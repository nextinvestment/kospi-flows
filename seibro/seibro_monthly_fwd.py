"""월별 순매수 TOP10 / 순매도 TOP10 바스켓의 forward 1M/3M/6M/12M 수익.
각 월 진입(월말) → +1/+3/+6/+12개월 등가중 수익. 전체월(2021~2026) 집계 +
매수 vs 매도 아웃퍼폼(호라이즌별). EODHD 월말 adjusted_close.
"""
import sys, time
from pathlib import Path
import pandas as pd, requests
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
from seibro_periodic_top10 import load_all, topn

H = {"1M": 1, "3M": 3, "6M": 6, "12M": 12}


def me_adj(tkr):
    try:
        r = requests.get(f"https://eodhd.com/api/eod/{tkr}",
            params={"api_token": EODHD_API_KEY, "fmt": "json", "from": "2021-01-01", "to": "2026-06-17"}, timeout=30)
        a = r.json() if r.status_code == 200 else []
        if not a: return None
        d = pd.DataFrame(a); d["date"] = pd.to_datetime(d["date"])
        c = "adjusted_close" if "adjusted_close" in d else "close"
        s = d.set_index("date")[c].sort_index().resample("ME").last()
        s.index = s.index.to_period("M").astype(str); return s
    except Exception:
        return None


def main():
    df = load_all()
    months = sorted(df["month"].unique())
    # monthly top10 memberships
    mem = {}
    keys = set()
    for m in months:
        b, s = topn(df[df.month == m])
        mem[m] = (list(b["key"]), list(s["key"]))
        keys |= set(b["key"]) | set(s["key"])
    # prices
    px = {}
    for k in sorted(keys):
        if not k or "·" in k or "?" in k or "(" in k or k.startswith("00"):
            continue
        sp = me_adj(k if "." in k else k + ".US")
        if sp is not None and len(sp) > 3:
            px[k] = sp
        time.sleep(0.03)
    print(f"가격 확보 {len(px)}/{len(keys)} 종목\n")

    def fwd(keylist, m, k):
        m2 = str(pd.Period(m, "M") + k); rets = []
        for key in keylist:
            sp = px.get(key)
            if sp is None or m not in sp.index or m2 not in sp.index: continue
            p0, p1 = sp[m], sp[m2]
            if pd.notna(p0) and pd.notna(p1) and p0 > 0: rets.append((p1/p0-1)*100)
        return sum(rets)/len(rets) if rets else None

    # aggregate per horizon
    print("##### 월별 매수/매도 바스켓 forward 수익 (전체월 평균, 등가중) #####")
    print(f"{'horizon':>8}{'매수평균':>9}{'매도평균':>9}{'아웃퍼폼':>9}{'매수승률':>8}{'표본월':>7}")
    agg = {}
    for h, k in H.items():
        bs, ss = [], []
        for m in months:
            bl, sl = mem[m]
            br, sr = fwd(bl, m, k), fwd(sl, m, k)
            if br is not None and sr is not None:
                bs.append(br); ss.append(sr)
        if bs:
            import statistics as st
            ba, sa = sum(bs)/len(bs), sum(ss)/len(ss)
            win = sum(1 for b, s in zip(bs, ss) if b > s)/len(bs)*100
            agg[h] = (ba, sa, ba-sa, win, len(bs))
            print(f"{h:>8}{ba:>+8.1f}%{sa:>+8.1f}%{ba-sa:>+8.1f}p{win:>7.0f}%{len(bs):>7}")

    # 최근 12개월 진입분만 (가능한 horizon만)
    print("\n##### 최근 12개월 진입분만 (forward 가능 구간) #####")
    last12 = months[-12:]
    for h, k in H.items():
        bs, ss, used = [], [], []
        for m in last12:
            bl, sl = mem[m]
            br, sr = fwd(bl, m, k), fwd(sl, m, k)
            if br is not None and sr is not None:
                bs.append(br); ss.append(sr); used.append(m)
        if bs:
            ba, sa = sum(bs)/len(bs), sum(ss)/len(ss)
            print(f"  {h}: 매수 {ba:+.1f}% / 매도 {sa:+.1f}% / 아웃퍼폼 {ba-sa:+.1f}p (n={len(bs)}월, ~{used[-1]})")
        else:
            print(f"  {h}: 표본 없음(아직 미도래)")


if __name__ == "__main__":
    main()
