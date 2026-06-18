"""월별 순매수 TOP10 vs 순매도 TOP10 바스켓 forward 1M/3M/6M/12M 수익 +
순매도 우위 케이스 카운트 + 그래프(PNG) 저장.
EODHD 월말 adjusted_close, 등가중. 진입=월말, +k개월 보유.
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

    # per-horizon aggregate + 케이스 카운트
    print("##### 월별 매수 vs 매도 바스켓 forward 수익 (전체월 평균, 등가중) #####")
    print(f"{'호라이즌':>8}{'매수평균':>9}{'매도평균':>9}{'매도-매수':>10}{'매도우위월':>11}{'표본월':>7}")
    agg = {}
    series = {}  # h -> list[(month, buy, sell)]
    for h, k in H.items():
        rows = []
        for m in months:
            bl, sl = mem[m]
            br, sr = fwd(bl, m, k), fwd(sl, m, k)
            if br is not None and sr is not None:
                rows.append((m, br, sr))
        if not rows: continue
        series[h] = rows
        bs = [r[1] for r in rows]; ss = [r[2] for r in rows]
        ba, sa = sum(bs)/len(bs), sum(ss)/len(ss)
        sell_win = sum(1 for _, b, s in rows if s > b)
        n = len(rows)
        agg[h] = (ba, sa, sa-ba, sell_win, n)
        print(f"{h:>8}{ba:>+8.1f}%{sa:>+8.1f}%{sa-ba:>+9.1f}p{sell_win:>6}/{n}월{n:>7}")

    # 케이스 요약
    print("\n##### 순매도 바스켓이 순매수보다 더 오른 케이스 #####")
    for h in H:
        if h in agg:
            ba, sa, sp, sw, n = agg[h]
            print(f"  {h}: {sw}/{n}월 ({sw/n*100:.0f}%)  · 평균 초과 {sp:+.1f}%p")

    # ---- 그래프 ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for fam in ("Malgun Gothic", "맑은 고딕", "Gulim"):
            try:
                matplotlib.rcParams["font.family"] = fam; break
            except Exception: pass
        matplotlib.rcParams["axes.unicode_minus"] = False

        fig, ax = plt.subplots(2, 2, figsize=(13, 9))
        hs = [h for h in H if h in agg]

        # (0,0) 평균 수익 그룹 막대
        x = range(len(hs)); w = 0.38
        bvals = [agg[h][0] for h in hs]; svals = [agg[h][1] for h in hs]
        ax[0,0].bar([i-w/2 for i in x], bvals, w, label="순매수 TOP10", color="#d62728")
        ax[0,0].bar([i+w/2 for i in x], svals, w, label="순매도 TOP10", color="#1f77b4")
        for i in x:
            ax[0,0].text(i-w/2, bvals[i], f"{bvals[i]:+.1f}", ha="center",
                         va="bottom" if bvals[i]>=0 else "top", fontsize=8)
            ax[0,0].text(i+w/2, svals[i], f"{svals[i]:+.1f}", ha="center",
                         va="bottom" if svals[i]>=0 else "top", fontsize=8)
        ax[0,0].set_xticks(list(x)); ax[0,0].set_xticklabels(hs)
        ax[0,0].axhline(0, color="k", lw=.6); ax[0,0].legend()
        ax[0,0].set_title("바스켓 평균 forward 수익 (전체월)"); ax[0,0].set_ylabel("%")

        # (0,1) 매도-매수 초과 + 매도우위 비율
        spr = [agg[h][2] for h in hs]
        bars = ax[0,1].bar(hs, spr, color=["#2ca02c" if v>0 else "#999" for v in spr])
        for i, h in enumerate(hs):
            sw, n = agg[h][3], agg[h][4]
            ax[0,1].text(i, spr[i], f"{spr[i]:+.1f}p\n매도우위 {sw}/{n}", ha="center",
                         va="bottom" if spr[i]>=0 else "top", fontsize=8)
        ax[0,1].axhline(0, color="k", lw=.6)
        ax[0,1].set_title("순매도 − 순매수 초과수익 (양수=매도가 더 오름)"); ax[0,1].set_ylabel("%p")

        # (1,0) 3M 진입월별 매수 vs 매도
        if "3M" in series:
            r = series["3M"]; mo = [x[0] for x in r]
            ax[1,0].plot(mo, [x[1] for x in r], color="#d62728", label="순매수", lw=1)
            ax[1,0].plot(mo, [x[2] for x in r], color="#1f77b4", label="순매도", lw=1)
            ax[1,0].axhline(0, color="k", lw=.6); ax[1,0].legend()
            step = max(1, len(mo)//12)
            ax[1,0].set_xticks(mo[::step]); ax[1,0].set_xticklabels(mo[::step], rotation=45, fontsize=7)
            ax[1,0].set_title("3M forward: 진입월별 매수 vs 매도"); ax[1,0].set_ylabel("%")

        # (1,1) 12M(없으면 6M) 진입월별 스프레드
        hh = "12M" if "12M" in series else "6M"
        if hh in series:
            r = series[hh]; mo = [x[0] for x in r]; sp2 = [x[2]-x[1] for x in r]
            ax[1,1].bar(mo, sp2, color=["#2ca02c" if v>0 else "#bbb" for v in sp2])
            ax[1,1].axhline(0, color="k", lw=.6)
            step = max(1, len(mo)//12)
            ax[1,1].set_xticks(mo[::step]); ax[1,1].set_xticklabels(mo[::step], rotation=45, fontsize=7)
            ax[1,1].set_title(f"{hh} forward: 매도−매수 스프레드(월별)"); ax[1,1].set_ylabel("%p")

        fig.suptitle("서학개미 월별 순매수 vs 순매도 바스켓 forward 수익 (2021~2026, EODHD)", fontsize=13)
        fig.tight_layout(rect=[0,0,1,0.97])
        out = HERE / "data" / "seibro_fwd_buyvssell.png"
        fig.savefig(out, dpi=130)
        print(f"\n그래프 저장: {out}")
    except Exception as ex:
        print(f"\n[그래프 실패] {ex}")


if __name__ == "__main__":
    main()
