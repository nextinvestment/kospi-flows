"""분기별 순매수/순매도 TOP10 재생성 — 라벨 정확화 + 검증 강제.

1) 데이터의 모든 ISIN을 EODHD로 티커 해석(미해결 캐시 확장).
2) ISIN 기준 분기 집계 → 순매수/순매도 TOP10, 라벨=실제 티커.
3) 검증: net==buy-sell / 같은 ISIN 양쪽 금지 / 같은 티커 양쪽 금지 / 미해결('?') 금지.
출력: 검증 리포트 + 마크다운표 + CSV.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import pandas as pd, requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent; DATA = HERE / "data"
sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
CACHE_F = DATA / "isin_ticker_cache.json"
CACHE = json.loads(CACHE_F.read_text(encoding="utf-8"))

# EODHD가 못 찾는 레버리지/인버스 ETF 등 수동 매핑 (이름 기준 확정).
# 분할 전후로 ISIN이 갈린 동일종목은 같은 라벨로 묶여 합산됨.
MANUAL = {
    "US25459W5408": "TMF",        # Direxion 20+yr Treasury Bull 3x
    "US74347G4322": "SQQQ", "US74350P6759": "SQQQ",   # ProShares UltraPro Short QQQ (split 전후)
    "US25460G3368": "SOXS", "US25460G1123": "SOXS", "US25461H5726": "SOXS",  # Semi Bear 3x
    "US5494981039": "LCID",       # Lucid
    "US74347Y7638": "BOIL",       # Ultra Bloomberg NatGas
    "US92864M4006": "ETHU", "US92864M7983": "ETHU",   # 2x Ether
    "US92891H6062": "UVIX",       # 2x Long VIX
    "US25461A3876": "KORU",       # Direxion Korea Bull 3x
    "JP3049130002": "TLT(JPYh)",  # iShares 20+yr Treasury JPY-hedged (TSE 2621)
    "US26923Q5642": "BMNR·2xL",   # T-Rex 2x Long BitMine
    "US88636V8431": "IONQ·2xS",   # Defiance 2x Short IONQ
    "US88636V6526": "RGTI·2xS",   # Defiance 2x Short Rigetti
    "US46092D3843": "TSLA·2xS",   # Tradr 2x Short TSLA
    "US87975E7765": "SPACE",      # Tema Space Innovators
    "US88636J4444": "TSLY",       # YieldMax TSLA Option Income
    "US88634T4931": "MSTY",       # YieldMax MSTR Option Income
    "US88636J2539": "MSTX",       # Defiance 1.75x Long MSTR
    "US25461A5285": "MUU",        # Direxion MU Bull 2x
}


def resolve(isin):
    if CACHE.get(isin):
        return CACHE[isin]
    try:
        r = requests.get(f"https://eodhd.com/api/search/{isin}",
                         params={"api_token": EODHD_API_KEY, "fmt": "json"}, timeout=20)
        res = r.json() if r.status_code == 200 else []
    except Exception:
        res = []
    us = [x for x in res if x.get("Exchange") in ("US", "NASDAQ", "NYSE", "BATS", "NYSE ARCA", "AMEX")]
    pick = (us or res)
    CACHE[isin] = f"{pick[0]['Code']}.{pick[0]['Exchange']}" if pick else None
    return CACHE[isin]


def main():
    u = pd.read_csv("verify_pkg/seibro_netbuy_monthly.csv", dtype={"month": str})
    for c in ["buy_usd", "sell_usd", "net_usd"]:
        u[c] = pd.to_numeric(u[c], errors="coerce")

    # 1) resolve every ISIN that can appear in any quarterly top10 (resolve all uniques)
    isins = u["isin"].dropna().unique().tolist()
    todo = [i for i in isins if not CACHE.get(i)]
    print(f"ISIN 총 {len(isins)}개, 미해결 {len(todo)}개 → EODHD 검색")
    for k, i in enumerate(todo, 1):
        resolve(i)
        if k % 10 == 0:
            CACHE_F.write_text(json.dumps(CACHE, ensure_ascii=False, indent=2), encoding="utf-8"); print(f"  {k}/{len(todo)}")
        time.sleep(0.05)
    CACHE_F.write_text(json.dumps(CACHE, ensure_ascii=False, indent=2), encoding="utf-8")

    def keydisp(isin, name):
        """key=병합단위(해결분은 티커→split 병합, 미해결분은 ISIN→병합금지), disp=표시명."""
        t = CACHE.get(isin)
        if t:
            k = t.split(".")[0]; return k, k
        if isin in MANUAL:
            return MANUAL[isin], MANUAL[isin]
        return isin, "?" + str(name)[:14]

    u["q"] = u["month"].map(lambda m: f"{m[:4]}Q{(int(m[5:7])-1)//3+1}")
    kd = u.apply(lambda r: keydisp(r["isin"], r["name"]), axis=1)
    u["key"] = [x[0] for x in kd]; u["disp"] = [x[1] for x in kd]

    # 2) quarterly aggregate by key (해결=티커병합 / 미해결=ISIN분리)
    rows, problems = [], []
    bad_net = u[((u.buy_usd - u.sell_usd) - u.net_usd).abs() > 1.5]
    if len(bad_net):
        problems.append(f"net!=buy-sell 행 {len(bad_net)}건")

    for q in sorted(u["q"].unique()):
        g = u[u.q == q].groupby("key", as_index=False).agg(
            net=("net_usd", "sum"), buy=("buy_usd", "sum"), sell=("sell_usd", "sum"), disp=("disp", "first"))
        buy10 = g.nlargest(10, "net"); sell10 = g.nsmallest(10, "net").sort_values("net")
        if set(buy10["key"]) & set(sell10["key"]):       # 같은 종목 양쪽 (구조상 불가)
            problems.append(f"{q}: 같은 종목 양쪽 {set(buy10['key'])&set(sell10['key'])}")
        miss = pd.concat([buy10, sell10])["disp"].str.startswith("?").sum()
        if miss:
            problems.append(f"{q}: 미해결 라벨 {miss}건")
        for side, sub in [("매수", buy10), ("매도", sell10)]:
            for rk, (_, r) in enumerate(sub.iterrows(), 1):
                rows.append({"q": q, "side": side, "rank": rk, "ticker": r["disp"],
                             "net_M": round(r["net"]/1e6), "buy_M": round(r["buy"]/1e6), "sell_M": round(r["sell"]/1e6)})
    o = pd.DataFrame(rows)
    o.to_csv("verify_pkg/seibro_quarterly_top10.csv", index=False, encoding="utf-8-sig")

    print("\n===== 검증 리포트 =====")
    print("문제:", problems if problems else "없음 ✅ (net=매수-매도, ISIN/티커 양쪽중복 없음, 미해결 없음)")
    print(f"미해결 ISIN 잔여: {sum(1 for i in isins if not CACHE.get(i))}/{len(isins)}")

    for q in sorted(o["q"].unique()):
        print(f"\n#### {q}  (순매수 / 매수 / 매도, $M)")
        print("|#|순매수 티커|net/매수/매도|순매도 티커|net/매수/매도|")
        print("|-|-|-|-|-|")
        bb = o[(o.q == q) & (o.side == "매수")].reset_index(drop=True)
        ss = o[(o.q == q) & (o.side == "매도")].reset_index(drop=True)
        for i in range(10):
            b, s = bb.iloc[i], ss.iloc[i]
            print(f"|{i+1}|{b['ticker']}|{b['net_M']:+d}/{b['buy_M']}/{b['sell_M']}|{s['ticker']}|{s['net_M']:+d}/{s['buy_M']}/{s['sell_M']}|")


if __name__ == "__main__":
    main()
