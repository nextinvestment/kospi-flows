"""최근 1달 / 3달 서학개미 순매수 TOP10 (라이브, SEIBRO).

윈도우 기간을 한 번의 fetch_top 호출로 서버집계(top-50 by 결제금액) → 티커라벨 →
순매수 내림차순 TOP10. today 기준 롤링.
"""
from __future__ import annotations
import sys
from datetime import date, timedelta

import seibro_fetcher as sf
from seibro_resolve import label_df

sys.stdout.reconfigure(encoding="utf-8")


def rank(start: str, end: str, top: int = 10):
    df = sf.fetch_top(start, end, top_n=50)
    if df.empty:
        print("  (데이터 없음)")
        return
    df = label_df(df)
    for c in ("NET", "BUY", "SELL"):
        pass
    df["net_M"] = df["SUM_FRSEC_NET_BUY_AMT"] / 1e6
    df["buy_M"] = df["SUM_FRSEC_BUY_AMT"] / 1e6
    df["sell_M"] = df["SUM_FRSEC_SELL_AMT"] / 1e6
    df = df.sort_values("net_M", ascending=False).head(top).reset_index(drop=True)
    print("|#|티커|순매수$M|매수$M|매도$M|종목명|")
    print("|-|-|-:|-:|-:|-|")
    for i, (_, r) in enumerate(df.iterrows(), 1):
        print(f"|{i}|{r['ticker']}|{r['net_M']:+,.0f}|{r['buy_M']:,.0f}|"
              f"{r['sell_M']:,.0f}|{r['KOR_SECN_NM'][:34]}|")


if __name__ == "__main__":
    today = date.today()
    d = today.strftime("%Y%m%d")
    m1 = (today - timedelta(days=30)).strftime("%Y%m%d")
    m3 = (today - timedelta(days=91)).strftime("%Y%m%d")

    print(f"### 최근 1달 순매수 TOP10  ({m1} → {d})")
    rank(m1, d)
    print()
    print(f"### 최근 3달 순매수 TOP10  ({m3} → {d})")
    rank(m3, d)
