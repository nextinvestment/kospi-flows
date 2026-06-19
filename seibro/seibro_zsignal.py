"""서학개미 순매수를 역발상 타이밍 신호로 정제.
- 순매수 z-score (trailing expanding / rolling-12, 룩어헤드 없음)
- scale-free 버전: 순매수/결제액 비율의 z (top50 데이터)
- z vs forward 나스닥수익 상관 + 버킷별 평균
- 역발상 타이밍 백테스트(z 낮을때 롱, 높을때 캐시) vs 바이앤홀드
"""
import sys
from pathlib import Path
import pandas as pd, numpy as np, requests
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
from seibro_periodic_top10 import load_all

# 사용자 제공 월별 순매수 ($M, 전체)
NB = {'2021-01':4532,'2021-02':2865,'2021-03':2780,'2021-04':2100,'2021-05':263,'2021-06':247,'2021-07':987,'2021-08':543,'2021-09':855,'2021-10':446,'2021-11':2694,'2021-12':2479,'2022-01':2467,'2022-02':3003,'2022-03':1636,'2022-04':2510,'2022-05':1860,'2022-06':408,'2022-07':-4,'2022-08':-572,'2022-09':291,'2022-10':198,'2022-11':478,'2022-12':-221,'2023-01':706,'2023-02':13,'2023-03':180,'2023-04':-337,'2023-05':-1026,'2023-06':-1061,'2023-07':-9,'2023-08':306,'2023-09':545,'2023-10':266,'2023-11':-487,'2023-12':-1922,'2024-01':730,'2024-02':1474,'2024-03':2095,'2024-04':993,'2024-05':463,'2024-06':2113,'2024-07':1101,'2024-08':499,'2024-09':-487,'2024-10':-761,'2024-11':1279,'2024-12':1046,'2025-01':4078,'2025-02':2975,'2025-03':4072,'2025-04':3705,'2025-05':-1311,'2025-06':-232,'2025-07':685,'2025-08':642,'2025-09':3184,'2025-10':6855,'2025-11':5934,'2025-12':1874,'2026-01':5003,'2026-02':3949,'2026-03':1692,'2026-04':-469,'2026-05':-940,'2026-06':-123}


def me(tkr):
    r = requests.get(f"https://eodhd.com/api/eod/{tkr}",
        params={"api_token": EODHD_API_KEY, "fmt": "json", "from": "2020-12-01", "to": "2026-06-18"}, timeout=30)
    d = pd.DataFrame(r.json()); d["date"] = pd.to_datetime(d["date"])
    s = d.set_index("date")["close"].sort_index().resample("ME").last()
    s.index = s.index.to_period("M").astype(str); return s


def trail_z(s, win=None, minp=6):
    """trailing z: t시점까지(포함) 통계로 표준화. win=None이면 확장(expanding)."""
    out = {}
    vals = s.values; idx = list(s.index)
    for i in range(len(idx)):
        lo = 0 if win is None else max(0, i - win + 1)
        hist = vals[lo:i+1]
        if len(hist) < minp:
            out[idx[i]] = np.nan; continue
        mu, sd = hist.mean(), hist.std(ddof=1)
        out[idx[i]] = (vals[i] - mu) / sd if sd > 0 else np.nan
    return pd.Series(out)


def main():
    nb = pd.Series(NB)
    ndx = me("IXIC.INDX")
    qqq = me("QQQ.US")

    # scale-free: 순매수/결제액 (top50)
    df = load_all()
    g = df.groupby("month").agg(net=("net","sum"), buy=("buy","sum"), sell=("sell","sum"))
    g["ratio"] = g["net"] / (g["buy"] + g["sell"]) * 100  # 순매수가 결제액의 몇 %

    z_exp = trail_z(nb, win=None)        # 확장 z (전체 순매수$)
    z_12 = trail_z(nb, win=12)           # 롤링12 z
    z_ratio = trail_z(g["ratio"], win=12)  # 비율 z

    base = pd.DataFrame({"nb": nb, "ndx": ndx, "z_exp": z_exp, "z_12": z_12,
                         "z_ratio": z_ratio}).dropna(subset=["ndx"])
    base["ret1"] = base["ndx"].pct_change().shift(-1) * 100   # 다음달 수익
    base["ret3"] = (base["ndx"].shift(-3)/base["ndx"]-1) * 100
    base["ret6"] = (base["ndx"].shift(-6)/base["ndx"]-1) * 100

    print("##### z 신호 vs forward 나스닥수익 상관 (음수=역발상 작동) #####")
    print(f"{'신호':>10}{'→ret1':>9}{'→ret3':>9}{'→ret6':>9}")
    for zc in ["z_exp", "z_12", "z_ratio"]:
        c1 = base[zc].corr(base["ret1"]); c3 = base[zc].corr(base["ret3"]); c6 = base[zc].corr(base["ret6"])
        print(f"{zc:>10}{c1:>+9.2f}{c3:>+9.2f}{c6:>+9.2f}")

    # 버킷별 (z_12 기준 3분위)
    print("\n##### z_12 3분위별 다음달/3M 나스닥 평균수익 #####")
    sub = base.dropna(subset=["z_12"]).copy()
    sub["bucket"] = pd.qcut(sub["z_12"], 3, labels=["저(매도과열)", "중", "고(매수과열)"])
    bt = sub.groupby("bucket", observed=True).agg(n=("z_12","size"), ret1=("ret1","mean"), ret3=("ret3","mean"))
    print(bt.round(1).to_string())

    # ----- 타이밍 백테스트 -----
    # 신호: z_12 <= 임계면 롱(다음달 QQQ), 아니면 캐시. 룩어헤드 없음(z는 당월, 수익은 다음달)
    bt2 = pd.DataFrame({"z": z_12, "qret": qqq.pct_change().shift(-1) * 100}).dropna()
    print("\n##### 역발상 타이밍 백테스트 (QQQ, 다음달 보유) #####")
    print(f"{'전략':>24}{'월수':>6}{'누적%':>9}{'연율%':>8}{'샤프':>7}{'롱비중':>7}")
    def stats(rets, name, expo=None):
        rets = rets.dropna()
        cum = (1 + rets/100).prod() - 1
        n = len(rets); cagr = ((1+cum)**(12/n)-1)*100
        sharpe = (rets.mean()/rets.std())*np.sqrt(12) if rets.std()>0 else 0
        ex = f"{expo*100:.0f}%" if expo is not None else "100%"
        print(f"{name:>24}{n:>6}{cum*100:>+9.1f}{cagr:>+8.1f}{sharpe:>7.2f}{ex:>7}")
        return cum
    stats(bt2["qret"], "바이앤홀드")
    for thr in [0.0, 0.5, 1.0]:
        sig = (bt2["z"] <= thr).astype(int)   # z 낮을때만 롱
        stats(bt2["qret"]*sig, f"z<= {thr} 롱/캐시", sig.mean())
    # 반대(추세추종) 비교
    sig = (bt2["z"] > 0.5).astype(int)
    stats(bt2["qret"]*sig, "z>0.5 롱(추세추종)", sig.mean())

    # ----- 그래프 -----
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        matplotlib.rcParams["font.family"] = "Malgun Gothic"; matplotlib.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(2, 1, figsize=(15, 10))
        b = base.dropna(subset=["z_12"]); x = range(len(b)); lab = list(b.index)
        col = ["#d62728" if v > 0 else "#1f77b4" for v in b["z_12"]]
        ax[0].bar(x, b["z_12"], color=col, width=0.8); ax[0].axhline(0, color="k", lw=.6)
        ax[0].axhline(1, color="r", ls="--", lw=.7); ax[0].axhline(-1, color="b", ls="--", lw=.7)
        ax[0].set_ylabel("순매수 z (롤링12)")
        ax2 = ax[0].twinx(); ax2.plot(x, b["ndx"], "k-", lw=1.4, label="나스닥")
        ax2.set_ylabel("나스닥"); ax2.legend(loc="upper left")
        st = max(1, len(x)//22); ax[0].set_xticks(list(x)[::st]); ax[0].set_xticklabels(lab[::st], rotation=45, fontsize=7)
        ax[0].set_title("순매수 z-score(역발상): 빨강=매수과열(약세신호) / 파랑=매도과열(강세신호)")

        # 누적 수익 곡선
        bt2c = bt2.copy(); idx2 = range(len(bt2c)); lab2 = list(bt2c.index)
        eq_bh = (1+bt2c["qret"]/100).cumprod()
        sig = (bt2c["z"] <= 0.5).astype(int)
        eq_z = (1+(bt2c["qret"]*sig)/100).cumprod()
        ax[1].plot(idx2, eq_bh, "k-", lw=1.6, label="바이앤홀드 QQQ")
        ax[1].plot(idx2, eq_z, "g-", lw=1.6, label="z<=0.5 롱/캐시(역발상)")
        ax[1].set_xticks(list(idx2)[::st]); ax[1].set_xticklabels(lab2[::st], rotation=45, fontsize=7)
        ax[1].legend(); ax[1].set_ylabel("누적 자산(배)"); ax[1].set_title("역발상 타이밍 vs 바이앤홀드")
        fig.suptitle("서학개미 순매수 역발상 z-신호", fontsize=14)
        fig.tight_layout(rect=[0,0,1,0.97])
        out = HERE / "data" / "seibro_zsignal.png"; fig.savefig(out, dpi=130); print(f"\n그래프: {out}")
    except Exception as ex:
        print(f"[그래프 실패] {ex}")


if __name__ == "__main__":
    main()
