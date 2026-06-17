"""레버리지/인버스 제외 후 월별 매수/매도 바스켓 forward 1M/3M/6M/12M.
제외 후 TOP10을 다시 선정(10종 유지). 두 설정: SOXL만 / 전체 레버리지·인버스.
"""
import sys, time, statistics as st
from pathlib import Path
import pandas as pd, requests
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
from seibro_periodic_top10 import load_all

H = {"1M": 1, "3M": 3, "6M": 6, "12M": 12}
LEV = {"SOXL","SOXS","TQQQ","SQQQ","TSLL","TSLT","NVDL","ETHU","BITX","MSTU","MSTX",
       "FNGU","BULZ","LABU","YINN","KORU","TMF","MUU","BOIL","KOLD","CONL","UVIX","UVXY",
       "UPRO","SPXL","SPXS","SPXU","SDOW","TZA","TNA","QLD","CWEB","SARK",
       "BMNR·2xL","IONQ·2xS","RGTI·2xS","TSLA·2xS"}


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


def memberships(df, exclude):
    sub = df[~df["key"].isin(exclude)]
    mem, keys = {}, set()
    for m, g in sub.groupby("month"):
        agg = g.groupby("key", as_index=False)["net"].sum()
        b = list(agg.nlargest(10, "net")["key"]); s = list(agg.nsmallest(10, "net")["key"])
        mem[m] = (b, s); keys |= set(b) | set(s)
    return mem, keys


def main():
    df = load_all()
    months = sorted(df["month"].unique())
    configs = {"SOXL만 제외": {"SOXL"}, "레버리지·인버스 전체 제외": LEV}

    # union keys for price fetch
    allkeys = set()
    mems = {}
    for name, ex in configs.items():
        mem, keys = memberships(df, ex); mems[name] = mem; allkeys |= keys

    px = {}
    for k in sorted(allkeys):
        if not k or "·" in k or "?" in k or "(" in k or k.startswith("00"):
            continue
        sp = me_adj(k if "." in k else k + ".US")
        if sp is not None and len(sp) > 3:
            px[k] = sp
        time.sleep(0.03)
    print(f"가격 확보 {len(px)}/{len(allkeys)}\n")

    def fwd(keylist, m, k):
        m2 = str(pd.Period(m, "M") + k); rr = []
        for key in keylist:
            sp = px.get(key)
            if sp is None or m not in sp.index or m2 not in sp.index: continue
            p0, p1 = sp[m], sp[m2]
            if pd.notna(p0) and pd.notna(p1) and p0 > 0: rr.append((p1/p0-1)*100)
        return sum(rr)/len(rr) if rr else None

    for name, mem in mems.items():
        print(f"##### {name} — 월별 매수/매도 바스켓 forward (전체월 평균) #####")
        print(f"{'보유':>6}{'매수':>9}{'매도':>9}{'아웃퍼폼':>9}{'매수승률':>8}{'표본':>6}")
        for h, k in H.items():
            bs, ss = [], []
            for m in months:
                bl, sl = mem.get(m, ([], []))
                br, sr = fwd(bl, m, k), fwd(sl, m, k)
                if br is not None and sr is not None:
                    bs.append(br); ss.append(sr)
            if bs:
                ba, sa = sum(bs)/len(bs), sum(ss)/len(ss)
                win = sum(1 for b, s in zip(bs, ss) if b > s)/len(bs)*100
                print(f"{h:>6}{ba:>+8.1f}%{sa:>+8.1f}%{ba-sa:>+8.1f}p{win:>7.0f}%{len(bs):>6}")
        print()


if __name__ == "__main__":
    main()
