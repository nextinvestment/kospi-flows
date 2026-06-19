"""서학개미 순매수 역발상 z-신호 — 2015~2026 장기 백테스트.
전 기간 SEIBRO top50 net합으로 통일(2015-2020 신규캐시 + 2021-2026 기존캐시).
rolling12 z, corr, 버킷, 연도별, 승률, 타이밍 백테스트, 그래프.
"""
import sys
from pathlib import Path
import pandas as pd, numpy as np, requests
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY


def load_netbuy():
    files = ["seibro_monthly_top25_2015_2020.csv", "seibro_monthly_top25_2021_2022.csv",
             "seibro_monthly_top25_2023.csv", "seibro_monthly_top25_2024-01_2026-05.csv"]
    frames = [pd.read_csv(HERE/"data"/f, dtype={"month": str}) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["net"] = pd.to_numeric(df["SUM_FRSEC_NET_BUY_AMT"], errors="coerce")
    s = df.groupby("month")["net"].sum() / 1e6  # $M
    return s.sort_index()


def me(t):
    r = requests.get(f"https://eodhd.com/api/eod/{t}",
        params={"api_token": EODHD_API_KEY, "fmt": "json", "from": "2013-12-01", "to": "2026-06-18"}, timeout=30)
    d = pd.DataFrame(r.json()); d["date"] = pd.to_datetime(d["date"])
    s = d.set_index("date")["close"].sort_index().resample("ME").last()
    s.index = s.index.to_period("M").astype(str); return s


def trail_z(s, win=12, minp=6):
    out = {}; vals = s.values; idx = list(s.index)
    for i in range(len(idx)):
        lo = max(0, i - win + 1); hist = vals[lo:i+1]
        if len(hist) < minp: out[idx[i]] = np.nan; continue
        mu, sd = hist.mean(), hist.std(ddof=1)
        out[idx[i]] = (vals[i]-mu)/sd if sd > 0 else np.nan
    return pd.Series(out)


def stats(rets):
    rets = rets.dropna(); cum = (1+rets/100).prod()-1; n = len(rets)
    cagr = ((1+cum)**(12/n)-1)*100; sh = (rets.mean()/rets.std())*np.sqrt(12) if rets.std()>0 else 0
    # max drawdown
    eq = (1+rets/100).cumprod(); dd = (eq/eq.cummax()-1).min()*100
    return cum*100, cagr, sh, dd


def main():
    nb = load_netbuy()
    qqq = me("QQQ.US"); ndx = me("IXIC.INDX")
    print(f"순매수 데이터: {nb.index[0]} ~ {nb.index[-1]} ({len(nb)}개월)")

    z = trail_z(nb, win=12)
    d = pd.DataFrame({"nb": nb, "z": z, "ndx": ndx}).dropna(subset=["ndx"])
    d["ret1"] = d["ndx"].pct_change().shift(-1)*100
    d["ret3"] = (d["ndx"].shift(-3)/d["ndx"]-1)*100

    print("\n##### z vs forward 나스닥수익 상관 #####")
    print(f"  →다음달 {d['z'].corr(d['ret1']):+.2f}  →3M {d['z'].corr(d['ret3']):+.2f}")

    print("\n##### z 3분위별 다음달/3M 평균 #####")
    s = d.dropna(subset=["z"]).copy(); s["b"] = pd.qcut(s["z"],3,labels=["저(매도과열)","중","고(매수과열)"])
    print(s.groupby("b",observed=True).agg(n=("z","size"),ret1=("ret1","mean"),ret3=("ret3","mean")).round(1).to_string())

    bt = pd.DataFrame({"z": z, "qret": qqq.pct_change().shift(-1)*100}).dropna()
    bt["ryear"] = [str(pd.Period(m,"M")+1)[:4] for m in bt.index]
    print(f"\n##### 백테스트 기간: {bt.index[0]}진입 ~ {bt.index[-1]}진입 ({len(bt)}개월) #####")
    print(f"{'전략':>22}{'누적%':>10}{'연율%':>8}{'샤프':>7}{'MDD%':>8}{'노출':>7}")
    c,g,sh,dd = stats(bt["qret"]); print(f"{'바이앤홀드':>22}{c:>+10.0f}{g:>+8.1f}{sh:>7.2f}{dd:>8.0f}{'100%':>7}")
    for thr in [0.0, 0.5, 1.0]:
        sig = (bt["z"]<=thr).astype(int); c,g,sh,dd = stats(bt["qret"]*sig)
        print(f"{f'z<= {thr} 롱/캐시':>22}{c:>+10.0f}{g:>+8.1f}{sh:>7.2f}{dd:>8.0f}{sig.mean()*100:>6.0f}%")
    sig = (bt["z"]>0.5).astype(int); c,g,sh,dd = stats(bt["qret"]*sig)
    print(f"{'z>0.5 롱(추세추종)':>22}{c:>+10.0f}{g:>+8.1f}{sh:>7.2f}{dd:>8.0f}{sig.mean()*100:>6.0f}%")

    # 연도별 (z<=0.5)
    for thr in [0.0, 0.5]:
        bt["sig"] = (bt["z"]<=thr).astype(int); bt["sret"] = bt["qret"]*bt["sig"]
        print(f"\n##### 연도별 (z<= {thr}) #####")
        print("| 연도 | B&H | 전략 | 차이 | 노출 |")
        print("|---|--:|--:|--:|--:|")
        for y,gr in bt.groupby("ryear"):
            bh=((1+gr["qret"]/100).prod()-1)*100; st=((1+gr["sret"]/100).prod()-1)*100
            print(f"| {y} | {bh:+.1f}% | {st:+.1f}% | {st-bh:+.1f}p | {gr['sig'].mean()*100:.0f}% |")
        lm=bt[bt["sig"]==1]; cm=bt[bt["sig"]==0]
        print(f"롱 적중(다음달+) {(lm['qret']>0).mean()*100:.0f}% (평균{lm['qret'].mean():+.1f}%) / 캐시 회피성공 {(cm['qret']<0).mean()*100:.0f}% (시장평균{cm['qret'].mean():+.1f}%)")

    # 그래프
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        matplotlib.rcParams["font.family"]="Malgun Gothic"; matplotlib.rcParams["axes.unicode_minus"]=False
        fig,ax=plt.subplots(2,1,figsize=(16,10))
        b=d.dropna(subset=["z"]); x=range(len(b)); lab=list(b.index)
        ax[0].bar(x,b["z"],color=["#d62728" if v>0 else "#1f77b4" for v in b["z"]],width=.85)
        ax[0].axhline(0,color="k",lw=.6); ax[0].axhline(1,color="r",ls="--",lw=.7); ax[0].axhline(-1,color="b",ls="--",lw=.7)
        a2=ax[0].twinx(); a2.plot(x,b["ndx"],"k-",lw=1.3,label="나스닥"); a2.legend(loc="upper left"); a2.set_yscale("log")
        st=max(1,len(x)//26); ax[0].set_xticks(list(x)[::st]); ax[0].set_xticklabels(lab[::st],rotation=45,fontsize=7)
        ax[0].set_ylabel("순매수 z(롤12)"); ax[0].set_title("순매수 z-score 2015~2026 (빨강=매수과열=약세신호)")
        eqb=(1+bt["qret"]/100).cumprod(); sig=(bt["z"]<=0.5).astype(int); eqz=(1+(bt["qret"]*sig)/100).cumprod()
        i2=range(len(bt)); l2=list(bt.index)
        ax[1].plot(i2,eqb,"k-",lw=1.6,label="바이앤홀드 QQQ"); ax[1].plot(i2,eqz,"g-",lw=1.6,label="z<=0.5 역발상")
        ax[1].set_yscale("log"); ax[1].legend(); ax[1].set_ylabel("누적(배,로그)")
        ax[1].set_xticks(list(i2)[::st]); ax[1].set_xticklabels(l2[::st],rotation=45,fontsize=7)
        ax[1].set_title("역발상 타이밍 vs 바이앤홀드 (2015~2026)")
        fig.suptitle("서학개미 순매수 역발상 z-신호 (2015~2026, top50 net)",fontsize=14)
        fig.tight_layout(rect=[0,0,1,0.97]); out=HERE/"data"/"seibro_zsignal_long.png"; fig.savefig(out,dpi=130); print(f"\n그래프: {out}")
    except Exception as ex: print(f"[그래프실패] {ex}")


if __name__ == "__main__":
    main()
