"""레버리지 신호 확장: 매수TOP10 롱레버 + 매도TOP10 롱레버.
- buy_lev: 순매수 TOP10 내 롱레버리지 수 (froth)
- sell_lev: 순매도 TOP10 내 롱레버리지 수 (디레버리징)
- churn = buy_lev + sell_lev
각각 forward QQQ 상관/버킷 + z결합 필터 재검토.
"""
import sys
from pathlib import Path
import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from seibro_periodic_top10 import topn
from seibro_monthly_full import load_all4, me_adj, zscore
from seibro_netbuy_nasdaq_2011 import NB

LONG_LEV = {"SOXL","TQQQ","TSLL","TSLT","NVDL","NVDU","ETHU","BITX","MSTU","MSTX","FNGU","BULZ",
            "LABU","YINN","KORU","UPRO","SPXL","TECL","WEBL","CWEB","QLD","BOIL","CONL","AGQ",
            "GDXU","TNA","NAIL","FAS","BITU","MUU"}

def llev(keys):
    c = 0
    for k in keys:
        kk = k.split("·")[0]
        if kk in LONG_LEV or k in LONG_LEV or "2xL" in k or "·2x" in k or "·3x" in k: c += 1
    return c

def stats(rets):
    rets = rets.dropna(); cum = (1+rets/100).prod()-1; n = len(rets)
    cagr = ((1+cum)**(12/n)-1)*100; sh = (rets.mean()/rets.std())*np.sqrt(12) if rets.std()>0 else 0
    eq = (1+rets/100).cumprod(); dd = (eq/eq.cummax()-1).min()*100
    return cum*100, cagr, sh, dd


def main():
    df = load_all4(); months = sorted(df["month"].unique())
    rec = {}
    for m in months:
        b, s = topn(df[df.month == m])
        rec[m] = (llev(list(b["key"])), llev(list(s["key"])))
    R = pd.DataFrame({m: rec[m] for m in months}, index=["buy_lev","sell_lev"]).T
    R["churn"] = R["buy_lev"] + R["sell_lev"]
    nb = pd.Series(NB); R["z"] = zscore(nb).reindex(R.index)
    qqq = me_adj("QQQ.US"); qret = qqq.pct_change().shift(-1)*100
    for h, k in {"1M":1,"3M":3,"6M":6}.items():
        R[f"q{h}"] = [(qqq[str(pd.Period(m,'M')+k)]/qqq[m]-1)*100
                      if m in qqq.index and str(pd.Period(m,'M')+k) in qqq.index else np.nan for m in R.index]

    print("##### 상관 vs forward QQQ #####")
    print(f"{'측정':>16}{'→1M':>8}{'→3M':>8}{'→6M':>8}")
    for col, nm in [("buy_lev","매수롱레버"),("sell_lev","매도롱레버"),("churn","churn(합)"),("z","순매수z")]:
        print(f"{nm:>16}"+"".join(f"{R[col].corr(R[f'q{h}']):>+8.2f}" for h in ["1M","3M","6M"]))

    print("\n##### 매도TOP10 롱레버 버킷별 forward QQQ (디레버리징=바닥?) #####")
    R["sb"] = pd.cut(R["sell_lev"], [-1,0,1,2,10], labels=["0","1","2","3+"])
    print(R.groupby("sb",observed=True).agg(n=("sell_lev","size"),q1M=("q1M","mean"),q3M=("q3M","mean"),q6M=("q6M","mean")).round(1).to_string())

    print("\n##### 매수TOP10 롱레버 버킷별 forward QQQ (froth=고점?) #####")
    R["bb"] = pd.cut(R["buy_lev"], [-1,0,1,2,10], labels=["0","1","2","3+"])
    print(R.groupby("bb",observed=True).agg(n=("buy_lev","size"),q1M=("q1M","mean"),q3M=("q3M","mean"),q6M=("q6M","mean")).round(1).to_string())

    # ===== 결합 필터 백테스트 =====
    bt = R.dropna(subset=["z"]).copy(); bt["qret"] = qret.reindex(bt.index)
    bt = bt.dropna(subset=["qret"]); bt["ry"] = [str(pd.Period(m,"M")+1)[:4] for m in bt.index]
    THR = 0.5
    sig = {
        "바이앤홀드": pd.Series(1, index=bt.index),
        "순수 z>0.5": (~(bt["z"] > THR)).astype(int),
        "AND z&매수레버≥4": (~((bt["z"] > THR) & (bt["buy_lev"] >= 4))).astype(int),
        "AND z&churn≥5": (~((bt["z"] > THR) & (bt["churn"] >= 5))).astype(int),
        "z&매수레버≥4, 단 매도레버≥3이면 롱유지": (
            ~((bt["z"] > THR) & (bt["buy_lev"] >= 4) & (bt["sell_lev"] < 3))).astype(int),
    }
    def run(pbt, label):
        print(f"\n### {label} (n={len(pbt)}) ###")
        print(f"{'전략':>34}{'누적%':>9}{'연율%':>8}{'샤프':>7}{'MDD%':>7}{'노출':>7}")
        for nm, s in sig.items():
            s2 = s.reindex(pbt.index); c,g,sh,dd = stats(pbt["qret"]*s2)
            print(f"{nm:>34}{c:>+9.0f}{g:>+8.1f}{sh:>7.2f}{dd:>7.0f}{s2.mean()*100:>6.0f}%")
    run(bt, f"전체 {bt.index[0]}~{bt.index[-1]}")
    run(bt[bt["ry"] >= "2021"], "2021~2026")

    # 매도레버 높은 달 (디레버리징 바닥 후보)
    print("\n##### 매도TOP10 롱레버 ≥3 인 달 (디레버리징) → 이후 #####")
    for m, r in R[R["sell_lev"] >= 3].iterrows():
        print(f"  {m} (매도레버={r['sell_lev']:.0f}) → QQQ 3M {r['q3M']:+.1f}% / 6M {r['q6M']:+.1f}%")


if __name__ == "__main__":
    main()
