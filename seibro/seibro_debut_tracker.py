"""서학개미 순매수 TOP10 '데뷔 추적기' (2023-01 ~ 2026-05).

각 종목이 언제 처음 순매수 TOP10에 등장했는지 + 그때 EODHD 주가 대비
이후(+3M/+6M/+1Y/현재) 성과. "유행 등장 타이밍이 좋았나 상투였나"를 숫자로.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import pandas as pd, requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent; DATA = HERE / "data"
sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
from seibro_fetcher import fetch_monthly_range

CACHE_F = DATA / "isin_ticker_cache.json"
CACHE = json.loads(CACHE_F.read_text(encoding="utf-8"))


def resolve(isin):
    if isin in CACHE: return CACHE[isin]
    try:
        r = requests.get(f"https://eodhd.com/api/search/{isin}",
            params={"api_token": EODHD_API_KEY, "fmt": "json"}, timeout=15)
        res = r.json() if r.status_code == 200 else []
    except Exception:
        res = []
    us = [x for x in res if x.get("Exchange") in ("US","NASDAQ","NYSE","BATS","NYSE ARCA","AMEX")]
    CACHE[isin] = (f"{(us or res)[0]['Code']}.{(us or res)[0]['Exchange']}") if (us or res) else None
    return CACHE[isin]


def adj(tkr, start="2023-01-01", end="2026-06-17"):
    try:
        r = requests.get(f"https://eodhd.com/api/eod/{tkr}",
            params={"api_token": EODHD_API_KEY, "fmt": "json", "from": start, "to": end}, timeout=30)
        arr = r.json() if r.status_code == 200 else []
        if not arr: return None
        d = pd.DataFrame(arr); d["date"] = pd.to_datetime(d["date"])
        c = "adjusted_close" if "adjusted_close" in d else "close"
        return d[["date", c]].rename(columns={c: "px"}).sort_values("date")
    except Exception:
        return None


def me_close(df, ym):
    if df is None: return None
    p = pd.Period(ym, freq="M")
    m = df[(df["date"] >= p.start_time) & (df["date"] <= p.end_time)]
    return float(m.iloc[-1]["px"]) if len(m) else None


def main():
    # 1) 2023 fetch (cache) + merge with existing 2024-01~2026-05
    f23 = DATA / "seibro_monthly_top25_2023.csv"
    if f23.exists():
        s23 = pd.read_csv(f23, dtype={"month": str, "ISIN": str})
    else:
        s23 = fetch_monthly_range("2023-01", "2023-12", top_n=25)
        s23.to_csv(f23, index=False, encoding="utf-8-sig")
    s24 = pd.read_csv(DATA / "seibro_monthly_top25_2024-01_2026-05.csv", dtype={"month": str, "ISIN": str})
    df = pd.concat([s23, s24], ignore_index=True)
    df["net"] = pd.to_numeric(df["SUM_FRSEC_NET_BUY_AMT"], errors="coerce")

    # 2) net-buy TOP10 per month
    top = df[df["net"].notna()].groupby("month", group_keys=False).apply(lambda g: g.nlargest(10, "net"))
    for isin in top["ISIN"].dropna().unique():
        if isin not in CACHE:
            resolve(isin); time.sleep(0.04)
    CACHE_F.write_text(json.dumps(CACHE, ensure_ascii=False, indent=2), encoding="utf-8")
    top["ticker"] = top["ISIN"].map(CACHE)

    # 3) per-ticker debut + stats
    agg = (top.dropna(subset=["ticker"]).groupby("ticker")
           .agg(name=("KOR_SECN_NM", "first"), debut=("month", "min"),
                months_in_top=("month", "nunique"), peak_net=("net", "max"),
                peak_month=("month", lambda s: top.loc[s.index].loc[top.loc[s.index, "net"].idxmax(), "month"]))
           .reset_index())

    # 4) prices
    print(f"가격 수집 {len(agg)} 티커…")
    px = {}
    for i, t in enumerate(agg["ticker"], 1):
        d = adj(t);
        if d is not None: px[t] = d
        time.sleep(0.04)

    rows = []
    for _, r in agg.iterrows():
        t = r["ticker"]; d0 = r["debut"]
        p0 = me_close(px.get(t), d0)
        if p0 is None: continue
        def fwd(k):
            p1 = me_close(px.get(t), str(pd.Period(d0, freq="M") + k))
            return (p1/p0 - 1)*100 if p1 else None
        cur = px[t].iloc[-1]["px"] if t in px else None
        rows.append({
            "ticker": t, "name": str(r["name"])[:22], "debut": d0,
            "months_in_top": int(r["months_in_top"]), "peak_month": r["peak_month"],
            "peak_net_M": round(r["peak_net"]/1e6), "px_at_debut": round(p0, 2),
            "ret_3M": fwd(3), "ret_6M": fwd(6), "ret_1Y": fwd(12),
            "ret_to_now": (cur/p0 - 1)*100 if cur else None,
        })
    out = pd.DataFrame(rows).sort_values("debut")
    out.to_csv(DATA / "seibro_debut_tracker.csv", index=False, encoding="utf-8-sig")

    fmt = lambda x: f"{x:+.0f}%" if pd.notna(x) else "  n/a"
    print(f"\n=== 서학개미 순매수 TOP10 데뷔 추적 (2023-01~2026-05), {len(out)}종 ===")
    print(f"{'debut':>8} {'종목':<22}{'#월':>4}{'데뷔가':>9}{'+3M':>7}{'+6M':>7}{'+1Y':>7}{'~현재':>8}{'peak$M':>8}")
    for _, r in out.iterrows():
        print(f"{r['debut']:>8} {r['name']:<22}{r['months_in_top']:>4}{r['px_at_debut']:>9.1f}"
              f"{fmt(r['ret_3M']):>7}{fmt(r['ret_6M']):>7}{fmt(r['ret_1Y']):>7}{fmt(r['ret_to_now']):>8}{r['peak_net_M']:>8}")


if __name__ == "__main__":
    main()
