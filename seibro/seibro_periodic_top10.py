"""서학개미 순매수/순매도 TOP10 — 최근 12개월 + 2021부터 분기별.
캐시된 월별 CSV(2021~2026)만 사용. 티커 매핑은 fix_quarterly_top10 재사용.
"""
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from fix_quarterly_top10 import CACHE, MANUAL

D = {'NVDA':'엔비디아','TSLA':'테슬라','MSFT':'MS','AAPL':'애플','GOOGL':'구글','META':'메타','AMZN':'아마존','AMD':'AMD','NFLX':'넷플릭스','MU':'마이크론','TSM':'TSMC','INTC':'인텔','AVGO':'브로드컴','QCOM':'퀄컴','ARM':'암','PLTR':'팔란티어','IONQ':'아이온큐/양자','RGTI':'리게티/양자','GME':'게임스톱','LCID':'루시드','SOUN':'사운드하운드','COIN':'코인베이스','MSTR':'스트래티지','UNH':'유나이티드헬스','CRCL':'서클/USDC','IREN':'아이리스/채굴','OKLO':'오클로/원전','SMR':'뉴스케일/원전','BMNR':'비트마인','NBIS':'네비우스','MRVL':'마벨','SNDK':'샌디스크','PFE':'화이자','O':'리얼티인컴','TEM':'템퍼스AI','BE':'블룸에너지','FRCB':'퍼스트리퍼블릭/파산','SCHD':'미국배당','ASML':'ASML','RKLB':'로켓랩','KO':'코카콜라','SBUX':'스타벅스','LLY':'일라이릴리','DJT':'트럼프미디어','HOOD':'로빈후드','ORCL':'오라클','SNPS':'시놉시스','SMCI':'슈퍼마이크로','NKE':'나이키','OXY':'옥시덴탈','BABA':'알리바바','NIO':'니오','AAL':'아메리칸항공','PLUG':'플러그파워','SOFI':'소파이',
'SPY':'S&P500','VOO':'S&P500저비용','QQQ':'나스닥100','QQQM':'나스닥100저비용','SOXX':'반도체지수','TQQQ':'나스닥3x롱','SOXL':'반도체3x롱','TSLL':'테슬라2x롱','TSLT':'테슬라2x롱','NVDL':'엔비디아2x롱','ETHU':'이더2x롱','BITX':'비트2x롱','MSTU':'스트래티지2x롱','MSTX':'스트래티지1.75x롱','BMNR·2xL':'비트마인2x롱','FNGU':'FANG+3x롱','BULZ':'빅테크3x롱','LABU':'바이오3x롱','YINN':'중국3x롱','KORU':'한국3x롱','TMF':'美장기채3x롱','MUU':'마이크론2x롱','DRAM':'메모리ETF','BOIL':'천연가스2x롱','CONL':'코인베이스2x롱','TQQQ':'나스닥3x롱','UPRO':'S&P500_3x롱','SPXL':'S&P500_3x롱','TECL':'기술주3x롱','WEBL':'인터넷3x롱','CWEB':'중국인터넷2x롱','TNA':'러셀2000_3x롱',
'SQQQ':'나스닥3x숏','SOXS':'반도체3x숏','UVIX':'VIX2x/헤지','KOLD':'천연가스2x숏','SPXS':'S&P500_3x숏','SPXU':'S&P500_3x숏','SDOW':'다우3x숏','TZA':'러셀2000_3x숏','SARK':'ARKK인버스',
'TLT':'美장기국채','TLT(JPYh)':'美장기채엔헤지','TLTW':'TLT커버드콜','SGOV':'초단기국채','BIL':'초단기국채','JEPI':'S&P500커버드콜','JEPQ':'나스닥커버드콜','TSLY':'YieldMax테슬라','ULTY':'YieldMax종합','SPACE':'우주ETF','ARKK':'ARK이노베이션','SCHD':'미국배당'}


def keydisp(isin, name):
    t = CACHE.get(isin)
    if t:
        k = t.split(".")[0]; return k, k
    if isin in MANUAL:
        return MANUAL[isin], MANUAL[isin]
    return isin, "?" + str(name)[:14]


def lab(t, desc=True):
    if not desc:
        return t
    d = D.get(t)
    return f"{t}({d})" if d else t


def load_all():
    files = ["seibro_monthly_top25_2021_2022.csv", "seibro_monthly_top25_2023.csv",
             "seibro_monthly_top25_2024-01_2026-05.csv"]
    frames = [pd.read_csv(HERE / "data" / f, dtype={"month": str, "ISIN": str}) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["net"] = pd.to_numeric(df["SUM_FRSEC_NET_BUY_AMT"], errors="coerce")
    df["buy"] = pd.to_numeric(df["SUM_FRSEC_BUY_AMT"], errors="coerce")
    df["sell"] = pd.to_numeric(df["SUM_FRSEC_SELL_AMT"], errors="coerce")
    kd = df.apply(lambda r: keydisp(r["ISIN"], r["KOR_SECN_NM"]), axis=1)
    df["key"] = [x[0] for x in kd]; df["disp"] = [x[1] for x in kd]
    return df


def topn(sub, n=10):
    g = sub.groupby("key", as_index=False).agg(net=("net","sum"), buy=("buy","sum"),
                                               sell=("sell","sum"), disp=("disp","first"))
    return g.nlargest(n, "net"), g.nsmallest(n, "net").sort_values("net")


def fmt(g, desc):
    return [(lab(r["disp"], desc), round(r["net"]/1e6), round(r["buy"]/1e6), round(r["sell"]/1e6))
            for _, r in g.iterrows()]


def main():
    df = load_all()
    months = sorted(df["month"].unique())
    print(f"데이터: {months[0]} ~ {months[-1]} ({len(months)}개월)")

    # ---- 최근 12개월 ----
    last12 = months[-12:]
    sub = df[df["month"].isin(last12)]
    b, s = topn(sub)
    print(f"\n##### 최근 12개월 ({last12[0]}~{last12[-1]}) 순매수/순매도 TOP10 ($M) #####")
    print("순매수 | net/매수/매도 || 순매도 | net/매수/매도")
    for (bn,bnet,bb,bs_),(sn,snet,sb,ss_) in zip(fmt(b,True), fmt(s,True)):
        print(f"  {bn:<22} {bnet:+6}/{bb}/{bs_}  ||  {sn:<22} {snet:+6}/{sb}/{ss_}")

    # ---- 분기별 2021~ ----
    df["q"] = df["month"].map(lambda m: f"{m[:4]}Q{(int(m[5:7])-1)//3+1}")
    print("\n\n##### 분기별 순매수/순매도 TOP10 (2021~, 티커만 / $M) #####")
    for q in sorted(df["q"].unique()):
        b, s = topn(df[df.q == q])
        print(f"\n### {q}")
        bl, sl = fmt(b, False), fmt(s, False)
        for i in range(10):
            bn,bnet,bb,bs_ = bl[i]; sn,snet,sb,ss_ = sl[i]
            print(f"{i+1:>2} {bn:<11}{bnet:+6}/{bb}/{bs_:<6} | {sn:<11}{snet:+6}/{sb}/{ss_}")


if __name__ == "__main__":
    main()
