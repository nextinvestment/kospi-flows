"""Build a self-contained verification package so an external reviewer (e.g. GPT)
can re-derive every number WITHOUT any API key.

Exports to seibro/verify_pkg/:
  - seibro_netbuy_monthly.csv : tidy SEIBRO monthly TOP25 (2023-01~2026-05),
        net-buy USD per (month, ISIN, name, ticker)  [the input universe]
  - prices_monthly.csv        : month-end adjusted_close matrix
        (index = YYYY-MM, columns = ticker, + SPY.US)  [enables recomputation]
  - debut_tracker.csv, buysell_top10.csv : my computed outputs (to be checked)
"""
from __future__ import annotations
import json, sys, time, shutil
from pathlib import Path
import pandas as pd, requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent; DATA = HERE / "data"
PKG = HERE / "verify_pkg"; PKG.mkdir(exist_ok=True)
sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
CACHE = json.loads((DATA / "isin_ticker_cache.json").read_text(encoding="utf-8"))


def adj_monthly(tkr):
    try:
        r = requests.get(f"https://eodhd.com/api/eod/{tkr}",
            params={"api_token": EODHD_API_KEY, "fmt": "json",
                    "from": "2023-01-01", "to": "2026-06-17"}, timeout=30)
        arr = r.json() if r.status_code == 200 else []
        if not arr: return None
        d = pd.DataFrame(arr); d["date"] = pd.to_datetime(d["date"])
        c = "adjusted_close" if "adjusted_close" in d else "close"
        s = d.set_index("date")[c].sort_index()
        m = s.resample("ME").last()
        m.index = m.index.to_period("M").astype(str)
        return m
    except Exception:
        return None


def main():
    # 1) merge SEIBRO 2023 + 2024-2026, tidy net-buy universe
    s23 = pd.read_csv(DATA / "seibro_monthly_top25_2023.csv", dtype={"month": str, "ISIN": str})
    s24 = pd.read_csv(DATA / "seibro_monthly_top25_2024-01_2026-05.csv", dtype={"month": str, "ISIN": str})
    df = pd.concat([s23, s24], ignore_index=True)
    df["ticker"] = df["ISIN"].map(CACHE)
    tidy = df[["month", "NATION_NM", "ISIN", "KOR_SECN_NM", "ticker",
               "SUM_FRSEC_BUY_AMT", "SUM_FRSEC_SELL_AMT", "SUM_FRSEC_NET_BUY_AMT"]].copy()
    tidy.columns = ["month", "nation", "isin", "name", "ticker",
                    "buy_usd", "sell_usd", "net_usd"]
    tidy.to_csv(PKG / "seibro_netbuy_monthly.csv", index=False, encoding="utf-8-sig")
    print(f"seibro_netbuy_monthly.csv: {len(tidy)} rows, {tidy['month'].nunique()} months")

    # 2) month-end price matrix for every ticker that ever appears + SPY
    tickers = sorted(set(tidy["ticker"].dropna())) + ["SPY.US"]
    print(f"fetching month-end prices for {len(tickers)} tickers…")
    cols = {}
    for i, t in enumerate(tickers, 1):
        m = adj_monthly(t)
        if m is not None: cols[t] = m
        if i % 25 == 0: print(f"  {i}/{len(tickers)}")
        time.sleep(0.04)
    pm = pd.DataFrame(cols)
    pm.index.name = "month"
    pm.to_csv(PKG / "prices_monthly.csv", encoding="utf-8-sig")
    print(f"prices_monthly.csv: {pm.shape[0]} months x {pm.shape[1]} tickers")

    # 3) copy my computed outputs + scripts
    for f in ["seibro_debut_tracker.csv", "seibro_buysell_top10_all.csv"]:
        if (DATA / f).exists():
            shutil.copy(DATA / f, PKG / f)
    for f in ["seibro_fetcher.py", "seibro_netbuy_perf.py", "seibro_debut_tracker.py"]:
        if (HERE / f).exists():
            shutil.copy(HERE / f, PKG / f)
    print("copied outputs + scripts")
    print("PKG:", PKG)


if __name__ == "__main__":
    main()
