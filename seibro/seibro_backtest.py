"""SEIBRO monthly TOP-N (Korean retail FX-stock buying) → 1-month-forward return via EODHD.

Pipeline:
  1. Fetch monthly TOP-N from SEIBRO via seibro_fetcher (지난 N개월)
  2. Resolve each unique ISIN → EODHD ticker (cached to disk)
  3. Pull historical closes from EODHD for every unique ticker
  4. For each (month, stock) pair:
       entry = last trading day of month (close)
       exit  = last trading day of month+1 (close)
       return = exit / entry - 1
  5. Aggregate stats (avg, median, win-rate, alpha vs SPY)

Universe choices:
  - "all"      : everything in SEIBRO data (incl. ETFs, leveraged products)
  - "stocks"   : equity only (skip ETFs/leveraged)  ← recommended
  - "us_only"  : NATION_NM == "미국"
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)
TICKER_CACHE = DATA / "isin_ticker_cache.json"

# Add provider from sibling stock-screener project
SCREENER = HERE.parent.parent / "stock-screener"
sys.path.insert(0, str(SCREENER))
from provider import EODHD_API_KEY  # noqa: E402

from seibro_fetcher import fetch_monthly_range  # noqa: E402


# --------------------------------------------------------------- ISIN resolution
def _load_cache() -> dict:
    if TICKER_CACHE.exists():
        return json.loads(TICKER_CACHE.read_text(encoding="utf-8"))
    return {}


def _save_cache(c: dict):
    TICKER_CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_isin(isin: str, cache: dict) -> str | None:
    """ISIN → EODHD ticker (e.g. 'NVDA.US'). Returns None if not resolvable."""
    if isin in cache:
        return cache[isin]
    try:
        r = requests.get(
            f"https://eodhd.com/api/search/{isin}",
            params={"api_token": EODHD_API_KEY, "fmt": "json"},
            timeout=15,
        )
        if r.status_code != 200:
            cache[isin] = None
            return None
        results = r.json()
    except Exception as e:
        print(f"  ! search {isin} failed: {e}")
        cache[isin] = None
        return None
    if not results:
        cache[isin] = None
        return None
    # prefer US exchange
    us = [x for x in results if x.get("Exchange") in ("US", "NASDAQ", "NYSE", "BATS", "NYSE ARCA", "AMEX")]
    picked = us[0] if us else results[0]
    tkr = f"{picked['Code']}.{picked['Exchange']}"
    cache[isin] = tkr
    return tkr


# --------------------------------------------------------------- Historical prices
def fetch_prices(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """Pull EOD historicals from EODHD for each ticker. Returns {ticker: df with date,close}."""
    out = {}
    for i, tkr in enumerate(tickers, 1):
        try:
            r = requests.get(
                f"https://eodhd.com/api/eod/{tkr}",
                params={"api_token": EODHD_API_KEY, "fmt": "json", "from": start, "to": end},
                timeout=30,
            )
            if r.status_code != 200:
                print(f"  ! {tkr} status {r.status_code}")
                continue
            arr = r.json()
            if not arr:
                continue
            df = pd.DataFrame(arr)
            df["date"] = pd.to_datetime(df["date"])
            out[tkr] = df[["date", "close"]].sort_values("date").reset_index(drop=True)
        except Exception as e:
            print(f"  ! {tkr} failed: {e}")
        if i % 25 == 0:
            print(f"  prices fetched: {i}/{len(tickers)}")
        time.sleep(0.05)
    return out


# --------------------------------------------------------------- Helpers
def month_end_close(df: pd.DataFrame, ym: str) -> float | None:
    p = pd.Period(ym, freq="M")
    m = df[(df["date"] >= p.start_time) & (df["date"] <= p.end_time)]
    if m.empty:
        return None
    return float(m.iloc[-1]["close"])


def is_etf_or_leveraged(name: str) -> bool:
    name = (name or "").upper()
    return any(k in name for k in [
        "ETF", "SHARES", "ETN", " 2X ", " 3X ", "BULL", "BEAR",
        "DIREXION", "PROSHARES", "DAILY", "TRADR", "ROUNDHILL", "TIGER",
        "INVERSE", "LEVERAGED", "VANECK", "GRANITESHARES",
    ])


# --------------------------------------------------------------- Backtest
def run(start_ym: str = "2024-01", end_ym: str | None = None, top_n: int = 25, mode: str = "stocks"):
    if end_ym is None:
        end_ym = pd.Timestamp.today().strftime("%Y-%m")
    print(f"=== SEIBRO {start_ym}~{end_ym} TOP{top_n} 백테스트 (mode={mode}) ===\n")

    # 1. Fetch SEIBRO monthly
    seibro_csv = DATA / f"seibro_monthly_top{top_n}_{start_ym}_{end_ym}.csv"
    if seibro_csv.exists():
        print(f"loading cached: {seibro_csv.name}")
        seibro = pd.read_csv(seibro_csv, dtype={"month": str, "ISIN": str})
    else:
        print("fetching from SEIBRO…")
        seibro = fetch_monthly_range(start_ym, end_ym, top_n=top_n)
        seibro.to_csv(seibro_csv, index=False, encoding="utf-8-sig")
    if seibro.empty:
        print("no SEIBRO data")
        return

    # Filter by mode
    if mode == "stocks":
        seibro = seibro[~seibro["KOR_SECN_NM"].apply(is_etf_or_leveraged)].reset_index(drop=True)
    elif mode == "us_only":
        seibro = seibro[seibro["NATION_NM"] == "미국"].reset_index(drop=True)
    print(f"filtered rows: {len(seibro)}, unique ISIN: {seibro['ISIN'].nunique()}")

    # 2. Resolve unique ISINs
    cache = _load_cache()
    isins = seibro["ISIN"].dropna().unique().tolist()
    new_resolves = 0
    for isin in isins:
        if isin not in cache:
            tkr = resolve_isin(isin, cache)
            new_resolves += 1
            if new_resolves % 10 == 0:
                _save_cache(cache)
            time.sleep(0.05)
    _save_cache(cache)
    seibro["ticker"] = seibro["ISIN"].map(cache)
    unresolved = seibro["ticker"].isna().sum()
    if unresolved:
        print(f"unresolved ISINs: {unresolved} rows ({seibro[seibro['ticker'].isna()]['ISIN'].nunique()} unique)")
    seibro = seibro[seibro["ticker"].notna()].copy()
    print(f"after ticker resolve: {len(seibro)} rows, {seibro['ticker'].nunique()} unique tickers")

    # 3. Historicals (start = first month, end = end_ym + 2 months)
    fetch_start = pd.Period(start_ym, freq="M").start_time.strftime("%Y-%m-%d")
    fetch_end = (pd.Period(end_ym, freq="M") + 2).end_time.strftime("%Y-%m-%d")
    tickers = seibro["ticker"].unique().tolist() + ["SPY.US"]
    print(f"\nfetching EODHD prices ({len(tickers)} tickers, {fetch_start} → {fetch_end})…")
    prices = fetch_prices(tickers, fetch_start, fetch_end)
    print(f"got {len(prices)} price series")

    # 4. Compute returns
    months = sorted(seibro["month"].unique())
    rows = []
    for i, m in enumerate(months[:-1]):  # need next month
        next_m = months[i + 1]
        top = seibro[seibro["month"] == m].nlargest(top_n, "SUM_FRSEC_TOT_AMT")
        for _, r in top.iterrows():
            tkr = r["ticker"]
            if tkr not in prices:
                continue
            p0 = month_end_close(prices[tkr], m)
            p1 = month_end_close(prices[tkr], next_m)
            if p0 is None or p1 is None:
                continue
            ret = (p1 / p0 - 1) * 100
            # SPY benchmark
            spy = prices.get("SPY.US")
            spy0 = month_end_close(spy, m) if spy is not None else None
            spy1 = month_end_close(spy, next_m) if spy is not None else None
            spy_ret = ((spy1 / spy0 - 1) * 100) if spy0 and spy1 else None
            rows.append({
                "month": m,
                "rnum": int(r["RNUM"]) if pd.notna(r["RNUM"]) else None,
                "name": r["KOR_SECN_NM"],
                "ticker": tkr,
                "settle_amt_usd": r["SUM_FRSEC_TOT_AMT"],
                "net_buy_usd": r["SUM_FRSEC_NET_BUY_AMT"],
                "entry": p0, "exit": p1,
                "ret_pct": ret,
                "spy_ret_pct": spy_ret,
                "alpha_pp": (ret - spy_ret) if spy_ret is not None else None,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        print("no returns computed")
        return

    # Per-month summary
    print("\n=== 월별 평균 ===")
    by_month = df.groupby("month").agg(
        picks=("ret_pct", "count"),
        avg_ret=("ret_pct", "mean"),
        median=("ret_pct", "median"),
        win_pct=("ret_pct", lambda x: (x > 0).mean() * 100),
        spy_ret=("spy_ret_pct", "mean"),
        alpha_pp=("alpha_pp", "mean"),
    ).reset_index()
    print(by_month.to_string(
        index=False,
        formatters={"avg_ret": "{:+.2f}".format, "median": "{:+.2f}".format,
                   "win_pct": "{:.1f}".format, "spy_ret": "{:+.2f}".format,
                   "alpha_pp": "{:+.2f}".format},
    ))

    # Overall
    print("\n=== Overall ===")
    print(f"총 픽: {len(df)}")
    print(f"평균 1M 수익률: {df['ret_pct'].mean():+.2f}%")
    print(f"중앙값:        {df['ret_pct'].median():+.2f}%")
    print(f"승률:          {(df['ret_pct'] > 0).mean() * 100:.1f}%")
    print(f"SPY 평균:      {df['spy_ret_pct'].mean():+.2f}%")
    print(f"Alpha:         {df['alpha_pp'].mean():+.2f}%p")
    print(f"최대 +수익:    {df['ret_pct'].max():+.2f}% ({df.loc[df['ret_pct'].idxmax(), 'name']}, {df.loc[df['ret_pct'].idxmax(), 'month']})")
    print(f"최대 -수익:    {df['ret_pct'].min():+.2f}% ({df.loc[df['ret_pct'].idxmin(), 'name']}, {df.loc[df['ret_pct'].idxmin(), 'month']})")

    out_csv = DATA / f"seibro_backtest_{mode}.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\nsaved per-pick detail: {out_csv}")


if __name__ == "__main__":
    args = sys.argv[1:]
    s = args[0] if len(args) > 0 else "2024-01"
    e = args[1] if len(args) > 1 else "2026-05"
    n = int(args[2]) if len(args) > 2 else 25
    mode = args[3] if len(args) > 3 else "stocks"
    run(s, e, top_n=n, mode=mode)
