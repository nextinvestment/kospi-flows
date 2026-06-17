"""순매수 TOP10 '첫 등장(데뷔)' 추적 — 2021부터 돌려 prior 확보, 2023부터 정리.

월별 순매수(net) TOP10에 각 종목이 처음 등장한 월을 계산.
2021-01~2022-12를 prior로 깔아, 2023+ 데뷔가 '진짜 첫 등장'이 되도록 함.
티커 병합/표시는 fix_quarterly_top10 의 CACHE+MANUAL 재사용.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent; DATA = HERE / "data"
sys.path.insert(0, str(HERE))
from seibro_fetcher import fetch_monthly_range
from fix_quarterly_top10 import CACHE, MANUAL, resolve, CACHE_F


def keydisp(isin, name):
    t = CACHE.get(isin)
    if t:
        k = t.split(".")[0]; return k, k
    if isin in MANUAL:
        return MANUAL[isin], MANUAL[isin]
    return isin, "?" + str(name)[:16]


def main():
    # 1) prior 2021-2022 (cache)
    f = DATA / "seibro_monthly_top25_2021_2022.csv"
    if f.exists():
        s2122 = pd.read_csv(f, dtype={"month": str, "ISIN": str})
    else:
        print("fetching SEIBRO 2021-01~2022-12 …")
        s2122 = fetch_monthly_range("2021-01", "2022-12", top_n=25)
        s2122.to_csv(f, index=False, encoding="utf-8-sig")

    s23 = pd.read_csv(DATA / "seibro_monthly_top25_2023.csv", dtype={"month": str, "ISIN": str})
    s24 = pd.read_csv(DATA / "seibro_monthly_top25_2024-01_2026-05.csv", dtype={"month": str, "ISIN": str})
    df = pd.concat([s2122, s23, s24], ignore_index=True)
    df["net"] = pd.to_numeric(df["SUM_FRSEC_NET_BUY_AMT"], errors="coerce")
    print(f"merged: {df['month'].min()} ~ {df['month'].max()}, {df['month'].nunique()} months, {len(df)} rows")

    # 2) resolve any new ISINs
    todo = [i for i in df["ISIN"].dropna().unique() if not CACHE.get(i)]
    for k, i in enumerate(todo, 1):
        resolve(i)
        if k % 15 == 0:
            CACHE_F.write_text(json.dumps(CACHE, ensure_ascii=False, indent=2), encoding="utf-8")
    CACHE_F.write_text(json.dumps(CACHE, ensure_ascii=False, indent=2), encoding="utf-8")

    kd = df.apply(lambda r: keydisp(r["ISIN"], r["KOR_SECN_NM"]), axis=1)
    df["key"] = [x[0] for x in kd]; df["disp"] = [x[1] for x in kd]

    # 3) monthly net-buy TOP10 by key
    rows = []
    for m, g in df.dropna(subset=["net"]).groupby("month"):
        agg = g.groupby("key", as_index=False).agg(net=("net", "sum"), disp=("disp", "first"))
        for _, r in agg.nlargest(10, "net").iterrows():
            rows.append({"month": m, "key": r["key"], "disp": r["disp"], "net_M": r["net"]/1e6})
    t10 = pd.DataFrame(rows)

    # 4) debut = first month in monthly net-buy TOP10
    debut = t10.sort_values("month").groupby("key", as_index=False).first()
    debut["appearances"] = debut["key"].map(t10["key"].value_counts())
    pre = set(debut[debut["month"] < "2023-01"]["key"])
    print(f"\n전체 데뷔 종목수 {len(debut)} | 2023 이전 prior 종목 {len(pre)}")

    # 5) list debuts from 2023-01 onward, chronological
    new = debut[debut["month"] >= "2023-01"].sort_values(["month", "net_M"], ascending=[True, False])
    print(f"\n=== 순매수 TOP10 첫 등장 (2023-01~2026-05), {len(new)}종 — 데뷔월순 ===")
    cur = None
    for _, r in new.iterrows():
        if r["month"] != cur:
            cur = r["month"]; print(f"\n[{cur}]")
        print(f"   {r['disp']:<18} 데뷔 net ${r['net_M']:+,.0f}M, 이후 TOP10 등장 {int(r['appearances'])}회")
    new.to_csv(DATA / "seibro_netbuy_debuts.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
