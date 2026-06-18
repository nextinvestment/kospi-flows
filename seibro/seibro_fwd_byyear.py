"""진입 연도별 매수 TOP10 vs 매도 TOP10 바스켓 forward 수익(1/3/6/12M).
각 월 코호트를 진입 '연도'로 묶어 연도별 평균 + 매도-매수 스프레드.
2026은 부분(진입 1~5월, 12M 미도래). EODHD adj close 월말.
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
    mem, keys = {}, set()
    for m in months:
        b, s = topn(df[df.month == m])
        mem[m] = (list(b["key"]), list(s["key"]))
        keys |= set(b["key"]) | set(s["key"])
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

    years = sorted({m[:4] for m in months})
    # year -> horizon -> (buy_avg, sell_avg, n)
    res = {y: {} for y in years}
    for y in years:
        ym = [m for m in months if m[:4] == y]
        for h, k in H.items():
            bs, ss = [], []
            for m in ym:
                bl, sl = mem[m]
                br, sr = fwd(bl, m, k), fwd(sl, m, k)
                if br is not None and sr is not None:
                    bs.append(br); ss.append(sr)
            if bs:
                res[y][h] = (sum(bs)/len(bs), sum(ss)/len(ss), len(bs))

    # ---- 표 출력 (markdown) ----
    def cell(y, h):
        if h not in res[y]: return "—"
        b, s, n = res[y][h]
        return f"{b:+.1f} / {s:+.1f} / **{s-b:+.1f}**"
    print("## 진입 연도별 forward 수익  (매수평균 / 매도평균 / **매도−매수**, %, 등가중)\n")
    print("| 진입연도 | n(월) | 1M | 3M | 6M | 12M |")
    print("|---|--:|---|---|---|---|")
    for y in years:
        n12 = res[y].get("12M", (0,0,0))[2]
        n1 = res[y].get("1M", (0,0,0))[2]
        print(f"| {y} | {n1} | {cell(y,'1M')} | {cell(y,'3M')} | {cell(y,'6M')} | {cell(y,'12M')}"
              + (f"  (n={n12})" if n12 and n12<n1 else "") + " |")

    # 스프레드만 요약(매도우위 +)
    print("\n## 연도별 매도−매수 스프레드만 (양수=매도바스켓이 더 오름)\n")
    print("| 진입연도 | 1M | 3M | 6M | 12M |")
    print("|---|--:|--:|--:|--:|")
    for y in years:
        def sp(h):
            return f"{res[y][h][1]-res[y][h][0]:+.1f}p" if h in res[y] else "—"
        print(f"| {y} | {sp('1M')} | {sp('3M')} | {sp('6M')} | {sp('12M')} |")

    # ---- 그래프: 연도별 3M·12M 스프레드 ----
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        matplotlib.rcParams["font.family"] = "Malgun Gothic"
        matplotlib.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(1, 2, figsize=(15, 6))
        for i, h in enumerate(["3M", "12M"]):
            ys = [y for y in years if h in res[y]]
            bv = [res[y][h][0] for y in ys]; sv = [res[y][h][1] for y in ys]
            x = range(len(ys)); w = 0.38
            ax[i].bar([j-w/2 for j in x], bv, w, label="매수 TOP10", color="#d62728")
            ax[i].bar([j+w/2 for j in x], sv, w, label="매도 TOP10", color="#1f77b4")
            for j in x:
                ax[i].text(j-w/2, bv[j], f"{bv[j]:+.0f}", ha="center", va="bottom" if bv[j]>=0 else "top", fontsize=8)
                ax[i].text(j+w/2, sv[j], f"{sv[j]:+.0f}", ha="center", va="bottom" if sv[j]>=0 else "top", fontsize=8)
            ax[i].set_xticks(list(x)); ax[i].set_xticklabels(ys)
            ax[i].axhline(0, color="k", lw=.6); ax[i].legend()
            ax[i].set_title(f"{h} forward: 진입연도별 매수 vs 매도"); ax[i].set_ylabel("%")
        fig.suptitle("서학개미 진입연도별 매수 vs 매도 바스켓 forward 수익", fontsize=13)
        fig.tight_layout(rect=[0,0,1,0.96])
        out = HERE / "data" / "seibro_fwd_byyear.png"
        fig.savefig(out, dpi=130); print(f"\n그래프: {out}")
    except Exception as ex:
        print(f"[그래프 실패] {ex}")


if __name__ == "__main__":
    main()
