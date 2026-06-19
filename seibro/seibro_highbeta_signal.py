"""순매수 TOP10 내 하이베타(레버리지/투기) 비중을 역발상 지표로 검토.
- 측정A: 레버리지/인버스 ETF 개수 (TOP10 중)
- 측정B: 레버리지 + 투기적 고베타 개별주 개수
각 월 카운트 → 고집중 시기 식별 + forward QQQ 수익 상관/버킷 + 순매수z와 결합.
"""
import sys, time
from pathlib import Path
import pandas as pd, numpy as np, requests
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
from seibro_periodic_top10 import keydisp, topn
from seibro_monthly_full import load_all4, me_adj, zscore
from seibro_netbuy_nasdaq_2011 import NB

# 레버리지/인버스 ETF (×2/×3, 롱/숏)
LEV = {"SOXL","SOXS","TQQQ","SQQQ","TSLL","TSLT","NVDL","NVDU","ETHU","BITX","MSTU","MSTX",
       "FNGU","FNGD","BULZ","LABU","YINN","YANG","KORU","TMF","MUU","CONL","UPRO","SPXL","SPXU",
       "SPXS","SDOW","TZA","TNA","TECL","WEBL","CWEB","QLD","QID","BOIL","KOLD","UVIX","UVXY",
       "SARK","AGQ","GDXU","BITU","ETHT","CONY","TSLY","NVDX","WANT","DPST","DRV","FAS","FAZ",
       "DFEN","NAIL","RETL","CURE","HIBL"}
# 투기적 고베타 개별주(밈/테마/프리IPO)
SPEC = {"IONQ","RGTI","QBTS","RIVN","LCID","SOUN","BMNR","IREN","CRCL","TEM","GME","PLTR","SMR",
        "OKLO","NBIS","SBET","JOBY","RKLB","ASTS","AAOI","RXRX","BE","COIN","MSTR","HOOD","NIO",
        "PLUG","DJT","FRCB","SPCX","RDW","FLNC","CONL","AMC","RBLX","U","SPACE","FIG","TTD"}


def lev_count(keys):
    c = 0
    for k in keys:
        kk = k.split("·")[0]
        if k in LEV or kk in LEV or "·2x" in k or "·3x" in k or "2xL" in k or "2xS" in k:
            c += 1
    return c


def spec_count(keys):  # 레버리지 + 투기
    c = 0
    for k in keys:
        kk = k.split("·")[0]
        if (k in LEV or kk in LEV or "·2x" in k or "2xL" in k or "2xS" in k or k in SPEC or kk in SPEC):
            c += 1
    return c


def main():
    df = load_all4()
    months = sorted(df["month"].unique())
    rows = []
    for m in months:
        b, s = topn(df[df.month == m])
        bl = list(b["key"])
        rows.append({"month": m, "lev": lev_count(bl), "spec": spec_count(bl), "top10": bl})
    R = pd.DataFrame(rows).set_index("month")

    nb = pd.Series(NB); z = zscore(nb)
    qqq = me_adj("QQQ.US")
    R["z"] = z.reindex(R.index)
    for h, k in {"1M":1,"3M":3,"6M":6}.items():
        R[f"q{h}"] = [ (qqq[str(pd.Period(m,'M')+k)]/qqq[m]-1)*100
                       if qqq is not None and m in qqq.index and str(pd.Period(m,'M')+k) in qqq.index else np.nan
                       for m in R.index ]

    # 고집중 시기
    print("##### 레버리지 ETF가 순매수 TOP10에 4개 이상인 달 #####")
    hi = R[R["lev"] >= 4]
    for m, r in hi.iterrows():
        levs = [k for k in r["top10"] if (k.split('·')[0] in LEV or k in LEV or '2xL' in k or '2xS' in k or '·2x' in k or '·3x' in k)]
        print(f"  {m} (lev={r['lev']}, spec={r['spec']}): {levs}")

    print("\n##### 상관: 하이베타 카운트 vs forward QQQ #####")
    print(f"{'측정':>12}{'→1M':>8}{'→3M':>8}{'→6M':>8}")
    for col, nm in [("lev","레버리지수"),("spec","레버+투기수")]:
        c = [R[col].corr(R[f"q{h}"]) for h in ["1M","3M","6M"]]
        print(f"{nm:>12}{c[0]:>+8.2f}{c[1]:>+8.2f}{c[2]:>+8.2f}")
    print(f"{'(참고)순매수z':>12}{R['z'].corr(R['q1M']):>+8.2f}{R['z'].corr(R['q3M']):>+8.2f}{R['z'].corr(R['q6M']):>+8.2f}")

    print("\n##### 레버리지수 버킷별 forward QQQ 평균 #####")
    R["bkt"] = pd.cut(R["lev"], [-1,0,1,2,3,10], labels=["0개","1개","2개","3개","4+개"])
    g = R.groupby("bkt", observed=True).agg(n=("lev","size"), q1M=("q1M","mean"), q3M=("q3M","mean"), q6M=("q6M","mean"))
    print(g.round(1).to_string())

    print("\n##### 레버+투기 버킷별 forward QQQ 평균 #####")
    R["bkt2"] = pd.cut(R["spec"], [-1,1,3,5,10], labels=["0-1개","2-3개","4-5개","6+개"])
    g2 = R.groupby("bkt2", observed=True).agg(n=("spec","size"), q1M=("q1M","mean"), q3M=("q3M","mean"), q6M=("q6M","mean"))
    print(g2.round(1).to_string())

    # 연도별 평균 카운트
    print("\n##### 연도별 평균 하이베타 카운트(순매수TOP10 중) #####")
    R["yr"] = [m[:4] for m in R.index]
    yg = R.groupby("yr").agg(레버리지=("lev","mean"), 레버투기=("spec","mean"))
    print(yg.round(1).to_string())

    R.drop(columns=["top10"]).to_csv(HERE/"data"/"seibro_highbeta_signal.csv", encoding="utf-8-sig")
    print(f"\n저장: data/seibro_highbeta_signal.csv")


if __name__ == "__main__":
    main()
