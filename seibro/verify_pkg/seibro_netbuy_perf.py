"""서학개미 순매수(net-buy) 월별 TOP10 → 1M/3M/6M/1Y 성과 (EODHD).

기존 seibro_backtest.py 대비:
  - 정렬을 SUM_FRSEC_NET_BUY_AMT(순매수) 기준으로 (결제금액 아님)
  - 보유기간 1M 외 3M/6M/1Y 동시 측정
  - adjusted_close 사용 (분할/배당 보정 — NVDA 2024-06 10:1 등)
캐시된 월별 CSV + ISIN 캐시 재사용, EODHD 가격만 새로 당김.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
DATA = HERE / "data"
sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY

CACHE = json.loads((DATA / "isin_ticker_cache.json").read_text(encoding="utf-8"))
HORIZONS = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12}


def is_etf_lev(name):
    name = (name or "").upper()
    return any(k in name for k in ["ETF","SHARES","ETN"," 2X "," 3X ","BULL","BEAR",
        "DIREXION","PROSHARES","DAILY","TRADR","ROUNDHILL","INVERSE","LEVERAGED","VANECK"])


def fetch_adj(tkr, start, end):
    try:
        r = requests.get(f"https://eodhd.com/api/eod/{tkr}",
            params={"api_token": EODHD_API_KEY, "fmt": "json", "from": start, "to": end}, timeout=30)
        if r.status_code != 200: return None
        arr = r.json()
        if not arr: return None
        df = pd.DataFrame(arr)
        df["date"] = pd.to_datetime(df["date"])
        col = "adjusted_close" if "adjusted_close" in df else "close"
        return df[["date", col]].rename(columns={col: "px"}).sort_values("date").reset_index(drop=True)
    except Exception:
        return None


def me_close(df, ym):
    if df is None: return None
    p = pd.Period(ym, freq="M")
    m = df[(df["date"] >= p.start_time) & (df["date"] <= p.end_time)]
    return float(m.iloc[-1]["px"]) if len(m) else None


def run(top_n=10, mode="all"):
    seibro = pd.read_csv(DATA / "seibro_monthly_top25_2024-01_2026-05.csv",
                         dtype={"month": str, "ISIN": str})
    seibro["net"] = pd.to_numeric(seibro["SUM_FRSEC_NET_BUY_AMT"], errors="coerce")
    if mode == "stocks":
        seibro = seibro[~seibro["KOR_SECN_NM"].apply(is_etf_lev)]
    seibro["ticker"] = seibro["ISIN"].map(CACHE)
    seibro = seibro[seibro["ticker"].notna() & seibro["net"].notna()]

    tickers = seibro["ticker"].unique().tolist() + ["SPY.US"]
    print(f"가격 수집: {len(tickers)} 티커 (adjusted_close)…")
    prices = {}
    for i, t in enumerate(tickers, 1):
        d = fetch_adj(t, "2024-01-01", "2026-06-17")
        if d is not None: prices[t] = d
        time.sleep(0.04)
    print(f"  {len(prices)} 시리즈 확보\n")

    months = sorted(seibro["month"].unique())
    rows = []
    for m in months:
        g = seibro[seibro["month"] == m]
        baskets = {"매수": g.nlargest(top_n, "net"), "매도": g.nsmallest(top_n, "net")}
        for side, top in baskets.items():
            for rank, (_, r) in enumerate(top.iterrows(), 1):
                t = r["ticker"]
                p0 = me_close(prices.get(t), m)
                if p0 is None: continue
                rec = {"month": m, "side": side, "rank": rank, "name": r["KOR_SECN_NM"],
                       "ticker": t, "net_usd": r["net"]}
                for h, k in HORIZONS.items():
                    tm = str(pd.Period(m, freq="M") + k)
                    p1 = me_close(prices.get(t), tm)
                    s0 = me_close(prices.get("SPY.US"), m); s1 = me_close(prices.get("SPY.US"), tm)
                    rec[h] = (p1/p0 - 1)*100 if p1 else None
                    rec[h+"_spy"] = (s1/s0 - 1)*100 if (s0 and s1) else None
                    rec[h+"_a"] = (rec[h] - rec[h+"_spy"]) if (rec[h] is not None and rec[h+"_spy"] is not None) else None
                rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_csv(DATA / f"seibro_buysell_top{top_n}_{mode}.csv", index=False, encoding="utf-8-sig")

    for side in ["매수", "매도"]:
        d = df[df["side"] == side]
        print(f"\n=== 서학개미 순{side} TOP{top_n} ({mode}) 성과: {months[0]}~{months[-1]} 진입 ===")
        print(f"{'horizon':>8}{'N':>5}{'평균':>9}{'중앙':>9}{'승률':>7}{'SPY':>9}{'알파':>9}")
        for h in HORIZONS:
            s = d[h].dropna(); a = d[h+"_a"].dropna(); sp = d[h+"_spy"].dropna()
            print(f"{h:>8}{len(s):>5}{s.mean():>+8.1f}%{s.median():>+8.1f}%"
                  f"{(s>0).mean()*100:>6.0f}%{sp.mean():>+8.1f}%{a.mean():>+8.1f}%p")

    print(f"\n=== 매수 vs 매도 스프레드 (매수알파 - 매도알파) ===")
    for h in HORIZONS:
        ab = df[df.side=="매수"][h+"_a"].dropna().mean()
        asl = df[df.side=="매도"][h+"_a"].dropna().mean()
        print(f"  {h}: 매수알파 {ab:+.1f}%p / 매도알파 {asl:+.1f}%p / 스프레드 {ab-asl:+.1f}%p")

    print("\n=== 최근 진입월 TOP10 ===")
    for side in ["매수", "매도"]:
        last = df[(df.month==df.month.max()) & (df.side==side)].sort_values("rank")
        print(f"  [순{side}]")
        for _, r in last.iterrows():
            oned = f"{r['1M']:+.1f}%" if pd.notna(r['1M']) else "n/a"
            print(f"   {r['rank']:>2} {r['name'][:20]:<22}{r['ticker']:<10} net ${r['net_usd']/1e6:>7,.0f}M  1M {oned}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    run(top_n=10, mode=mode)
