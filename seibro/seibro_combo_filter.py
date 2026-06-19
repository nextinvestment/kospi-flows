"""순매수 z + 롱레버리지 카운트 결합 필터 백테스트.
- 순수 z: z>thr면 캐시
- AND: z>thr AND 롱레버≥L 일때만 캐시 (회피를 더 선별적으로 → 강세장 더 참여)
- OR: z>thr OR 롱레버≥L 이면 캐시
QQQ 다음달 보유. 룩어헤드 없음.
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
    lev = {}
    for m in months:
        b, _ = topn(df[df.month == m]); lev[m] = llev(list(b["key"]))
    nb = pd.Series(NB); z = zscore(nb); qqq = me_adj("QQQ.US")
    qret = qqq.pct_change().shift(-1)*100

    bt = pd.DataFrame({"z": z, "lev": pd.Series(lev), "qret": qret}).dropna()
    bt["ry"] = [str(pd.Period(m, "M")+1)[:4] for m in bt.index]

    THR, L = 0.5, 4
    sig = {
        "바이앤홀드": pd.Series(1, index=bt.index),
        f"순수 z>{THR}회피": (~(bt["z"] > THR)).astype(int),
        f"AND (z>{THR} & lev≥{L})": (~((bt["z"] > THR) & (bt["lev"] >= L))).astype(int),
        f"OR (z>{THR} | lev≥{L})": (~((bt["z"] > THR) | (bt["lev"] >= L))).astype(int),
        f"레버only (lev≥{L} 회피)": (~(bt["lev"] >= L)).astype(int),
    }

    def run(period_bt, label):
        print(f"\n### {label} ###")
        print(f"{'전략':>22}{'누적%':>9}{'연율%':>8}{'샤프':>7}{'MDD%':>7}{'노출':>7}")
        for nm, s in sig.items():
            s2 = s.reindex(period_bt.index)
            c, g, sh, dd = stats(period_bt["qret"]*s2)
            print(f"{nm:>22}{c:>+9.0f}{g:>+8.1f}{sh:>7.2f}{dd:>7.0f}{s2.mean()*100:>6.0f}%")

    run(bt, f"전체 {bt.index[0]}~{bt.index[-1]} 진입 (n={len(bt)})")
    run(bt[bt["ry"] >= "2021"], "2021~2026 진입분만")

    # 연도별 (AND vs 순수 z vs B&H)
    print("\n##### 연도별 수익 (B&H / 순수z / AND결합) #####")
    print("| 연도 | B&H | 순수z회피 | AND결합 | AND노출 |")
    print("|---|--:|--:|--:|--:|")
    sz = sig[f"순수 z>{THR}회피"]; sand = sig[f"AND (z>{THR} & lev≥{L})"]
    for y, gr in bt.groupby("ry"):
        bh = ((1+gr["qret"]/100).prod()-1)*100
        zr = ((1+(gr["qret"]*sz.reindex(gr.index))/100).prod()-1)*100
        ar = ((1+(gr["qret"]*sand.reindex(gr.index))/100).prod()-1)*100
        print(f"| {y} | {bh:+.1f}% | {zr:+.1f}% | {ar:+.1f}% | {sand.reindex(gr.index).mean()*100:.0f}% |")

    # AND가 회피한 달 목록
    avoid = bt[(bt["z"] > THR) & (bt["lev"] >= L)]
    print(f"\n##### AND 회피 발동 달 (z>{THR} & lev≥{L}): {len(avoid)}개 #####")
    for m, r in avoid.iterrows():
        print(f"  {m} (z={r['z']:+.2f}, lev={r['lev']:.0f}) → 다음달 QQQ {r['qret']:+.1f}%")


if __name__ == "__main__":
    main()
