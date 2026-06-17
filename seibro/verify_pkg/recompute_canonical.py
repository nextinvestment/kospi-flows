"""Recompute ALL reported numbers from the bundled files ONLY (no API, no cache),
so the package is internally self-consistent and GPT-reproducible.
Overwrites seibro_buysell_top10_all.csv and seibro_debut_tracker.csv in this folder.
"""
import sys
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")

u = pd.read_csv("seibro_netbuy_monthly.csv", dtype={"month": str})
px = pd.read_csv("prices_monthly.csv", dtype={"month": str}).set_index("month")
H = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12}


def ret(t, m, k):
    m2 = str(pd.Period(m, "M") + k)
    if t not in px.columns or m not in px.index or m2 not in px.index:
        return None
    p0, p1 = px.at[m, t], px.at[m2, t]
    return (p1 / p0 - 1) * 100 if pd.notna(p0) and pd.notna(p1) else None


# ---------- buy/sell TOP10 (2024-01~2026-05) ----------
rows = []
for m, g in u.dropna(subset=["ticker", "net_usd"]).groupby("month"):
    if m < "2024-01":
        continue
    for side, top in [("매수", g.nlargest(10, "net_usd")), ("매도", g.nsmallest(10, "net_usd"))]:
        for rank, (_, r) in enumerate(top.iterrows(), 1):
            rec = {"month": m, "side": side, "rank": rank, "name": r["name"],
                   "ticker": r["ticker"], "net_usd": r["net_usd"]}
            for h, k in H.items():
                rec[h] = ret(r["ticker"], m, k)
                s = ret("SPY.US", m, k)
                rec[h + "_spy"] = s
                rec[h + "_a"] = (rec[h] - s) if (rec[h] is not None and s is not None) else None
            rows.append(rec)
bs = pd.DataFrame(rows)
bs.to_csv("seibro_buysell_top10_all.csv", index=False, encoding="utf-8-sig")

print("=== 매수/매도 TOP10 (canonical, from bundled prices) ===")
for side in ["매수", "매도"]:
    d = bs[bs.side == side]
    print(f"[{side}]")
    for h in H:
        s = d[h].dropna()
        print(f"  {h}: N={len(s)} 평균 {s.mean():+.1f}% 중앙 {s.median():+.1f}% "
              f"승률 {(s>0).mean()*100:.0f}% SPY {d[h+'_spy'].dropna().mean():+.1f}% alpha {d[h+'_a'].dropna().mean():+.1f}%p")
print("스프레드(매수alpha-매도alpha):")
for h in H:
    ab = bs[bs.side=="매수"][h+"_a"].dropna().mean(); asl = bs[bs.side=="매도"][h+"_a"].dropna().mean()
    print(f"  {h}: {ab-asl:+.1f}%p")

# ---------- debut tracker (2023-01~2026-05) ----------
top10 = (u.dropna(subset=["ticker", "net_usd"]).groupby("month", group_keys=False)
         .apply(lambda g: g.nlargest(10, "net_usd"), include_groups=False))
# include_groups=False drops 'month'; recover via index alignment
top10 = u.dropna(subset=["ticker","net_usd"]).groupby("month",group_keys=False).apply(lambda g: g.nlargest(10,"net_usd"))
deb = []
for t, g in top10.groupby("ticker"):
    d0 = g["month"].min()
    p0 = px.at[d0, t] if (t in px.columns and d0 in px.index and pd.notna(px.at[d0, t])) else None
    if p0 is None:
        continue
    cur = px[t].dropna().iloc[-1] if t in px.columns and px[t].notna().any() else None
    deb.append({"ticker": t, "name": g["name"].iloc[0][:24], "debut": d0,
                "months_in_top": g["month"].nunique(),
                "px_at_debut": round(p0, 2),
                "ret_3M": ret(t, d0, 3), "ret_6M": ret(t, d0, 6), "ret_1Y": ret(t, d0, 12),
                "ret_to_now": (cur/p0-1)*100 if cur is not None else None})
deb = pd.DataFrame(deb).sort_values("debut")
deb.to_csv("seibro_debut_tracker.csv", index=False, encoding="utf-8-sig")
print(f"\n데뷔추적 {len(deb)}종 재생성. 스폿체크:")
for t in ["NVDA.US","MU.US","SOXL.US","CRCL.US"]:
    r = deb[deb.ticker==t]
    if len(r):
        r=r.iloc[0]; print(f"  {t}: debut {r['debut']} @{r['px_at_debut']} → now {r['ret_to_now']:+.0f}%")
