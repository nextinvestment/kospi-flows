"""서학개미 종합:
 1) 2021~ 분기별 매수/매도 TOP10 (net/매수/매도) → CSV
 2) 분기별 BEST (#1 순매수 / #1 순매도)
 3) 최근 12개월 월별 매수/매도 TOP10
 4) 매수 vs 매도 아웃퍼폼: 각 분기 net-buy TOP10 / net-sell TOP10 바스켓의
    '다음 분기' 등가중 수익률 비교 (EODHD 월말 adjusted_close).
"""
import sys, time
from pathlib import Path
import pandas as pd, requests

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
from seibro_periodic_top10 import load_all, lab, topn, D


def qpath(q):  # 'YYYYQn' -> last month 'YYYY-MM'
    y, n = q.split("Q"); return f"{y}-{int(n)*3:02d}"


def me_adj(tkr):
    try:
        r = requests.get(f"https://eodhd.com/api/eod/{tkr}",
            params={"api_token": EODHD_API_KEY, "fmt": "json",
                    "from": "2021-01-01", "to": "2026-06-17"}, timeout=30)
        a = r.json() if r.status_code == 200 else []
        if not a: return None
        d = pd.DataFrame(a); d["date"] = pd.to_datetime(d["date"])
        c = "adjusted_close" if "adjusted_close" in d else "close"
        s = d.set_index("date")[c].sort_index().resample("ME").last()
        s.index = s.index.to_period("M").astype(str)
        return s
    except Exception:
        return None


def main():
    df = load_all()
    df["q"] = df["month"].map(lambda m: f"{m[:4]}Q{(int(m[5:7])-1)//3+1}")
    quarters = sorted(df["q"].unique())
    months = sorted(df["month"].unique())

    # ---- 1) quarterly full → CSV + collect rows ----
    rows = []
    for q in quarters:
        b, s = topn(df[df.q == q])
        for side, g in [("매수", b), ("매도", s)]:
            for rk, (_, r) in enumerate(g.iterrows(), 1):
                rows.append({"q": q, "side": side, "rank": rk, "ticker": r["disp"],
                             "net_M": round(r["net"]/1e6), "buy_M": round(r["buy"]/1e6),
                             "sell_M": round(r["sell"]/1e6)})
    qdf = pd.DataFrame(rows)
    qdf.to_csv(HERE / "data" / "seibro_quarterly_2021_2026.csv", index=False, encoding="utf-8-sig")
    print(f"[1] 분기별 풀세트 저장: seibro_quarterly_2021_2026.csv ({len(qdf)}행)")

    # ---- 2) 분기별 BEST ----
    print("\n##### [2] 분기별 BEST (#1 순매수 / #1 순매도, $M net/매수/매도) #####")
    for q in quarters:
        bb = qdf[(qdf.q==q)&(qdf.side=="매수")].iloc[0]
        ss = qdf[(qdf.q==q)&(qdf.side=="매도")].iloc[0]
        print(f"{q}: 매수 {lab(bb.ticker)} {bb.net_M:+}/{bb.buy_M}/{bb.sell_M}"
              f"  ||  매도 {lab(ss.ticker)} {ss.net_M:+}/{ss.buy_M}/{ss.sell_M}")

    # ---- 3) 최근 12개월 월별 TOP10 ----
    print("\n\n##### [3] 최근 12개월 월별 매수/매도 TOP10 ($M net) #####")
    for m in months[-12:]:
        b, s = topn(df[df.month == m])
        bl = [f"{lab(r['disp'],False)}{round(r['net']/1e6):+}" for _, r in b.iterrows()]
        sl = [f"{lab(r['disp'],False)}{round(r['net']/1e6):+}" for _, r in s.iterrows()]
        print(f"\n[{m}]")
        print("  매수: " + " · ".join(bl))
        print("  매도: " + " · ".join(sl))

    # ---- 4) 매수 vs 매도 아웃퍼폼 (다음 분기 등가중 수익률) ----
    print("\n\n[4] 가격 수집 중 (아웃퍼폼 측정)…")
    keys = set()
    for q in quarters:
        b, s = topn(df[df.q == q])
        keys |= set(b["key"]) | set(s["key"])
    # fetch month-end prices: key -> key.US (대부분 미국상장), 특수문자/미해결 제외
    px = {}
    for k in sorted(keys):
        if not k or "·" in k or "?" in k or "(" in k or k.startswith("00"):
            continue
        sym = k if "." in k else k + ".US"
        sp = me_adj(sym)
        if sp is not None and len(sp) > 3:
            px[k] = sp
        time.sleep(0.03)
    print(f"  가격 확보 {len(px)}/{len(keys)} 종목")

    def basket_fwd(keys_list, q):
        m0 = qpath(q); m1 = qpath(quarters[quarters.index(q)+1])
        rets = []
        for k in keys_list:
            sp = px.get(k)
            if sp is None or m0 not in sp.index or m1 not in sp.index:
                continue
            p0, p1 = sp[m0], sp[m1]
            if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                rets.append((p1/p0 - 1)*100)
        return (sum(rets)/len(rets), len(rets)) if rets else (None, 0)

    print("\n##### [4] 분기별 매수바스켓 vs 매도바스켓 — 다음분기 등가중 수익률 #####")
    print(" 분기 | 매수바스켓 | 매도바스켓 | 매수-매도(아웃퍼폼)")
    diffs, brs, srs = [], [], []
    for q in quarters[:-1]:
        b, s = topn(df[df.q == q])
        br, bn = basket_fwd(list(b["key"]), q)
        sr, sn = basket_fwd(list(s["key"]), q)
        if br is None or sr is None:
            continue
        d = br - sr; diffs.append(d); brs.append(br); srs.append(sr)
        print(f" {q} | 매수 {br:+6.1f}% (n{bn}) | 매도 {sr:+6.1f}% (n{sn}) | {d:+6.1f}%p")
    if diffs:
        import statistics as st
        print(f"\n 평균: 매수바스켓 {sum(brs)/len(brs):+.1f}% / 매도바스켓 {sum(srs)/len(srs):+.1f}%"
              f" / 아웃퍼폼 {sum(diffs)/len(diffs):+.1f}%p (중앙 {st.median(diffs):+.1f}%p)")
        print(f" 매수>매도 분기: {sum(1 for d in diffs if d>0)}/{len(diffs)}")


if __name__ == "__main__":
    main()
