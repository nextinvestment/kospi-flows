"""주간(월~금) 서학개미 순위 — west-ant 식 순매수 정렬 + 결제금액 정렬 둘 다, 티커 표시.

사용:
    python seibro_week.py                # 이번 주(월~오늘) 자동
    python seibro_week.py 20260622 20260626   # 직접 지정

출처: SEIBRO getImptFrcurStkSetlAmtList (외화증권 결제금액, 단위 USD).
한계: SEIBRO가 결제금액 상위 50종목만 반환(페이지네이션 무효).
"""
from __future__ import annotations
import sys
from datetime import date, timedelta

import pandas as pd

import seibro_fetcher as sf
from seibro_resolve import label_df

sys.stdout.reconfigure(encoding="utf-8")


def this_week_mon_fri(today: date | None = None) -> tuple[str, str]:
    """이번 주 월요일 ~ min(금요일, 오늘)."""
    today = today or date.today()
    mon = today - timedelta(days=today.weekday())     # weekday(): 월=0
    fri = mon + timedelta(days=4)
    end = min(fri, today)
    return mon.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def weekly_ranking(start: str, end: str, top: int = 15) -> pd.DataFrame:
    df = sf.fetch_top(start, end, top_n=50)
    if df.empty:
        return df
    df = label_df(df)
    df["net_M"] = df["SUM_FRSEC_NET_BUY_AMT"] / 1e6
    df["tot_M"] = df["SUM_FRSEC_TOT_AMT"] / 1e6
    df["buy_M"] = df["SUM_FRSEC_BUY_AMT"] / 1e6
    df["sell_M"] = df["SUM_FRSEC_SELL_AMT"] / 1e6
    return df


def print_netbuy_ranking(df):
    """순매수 내림차순 전체 순위 (west-ant 식)."""
    df = df.sort_values("net_M", ascending=False).reset_index(drop=True)
    print("|#|티커|순매수$M|매수$M|매도$M|종목명|")
    print("|-|-|-:|-:|-:|-|")
    for i, (_, r) in enumerate(df.iterrows(), 1):
        print(f"|{i}|{r['ticker']}|{r['net_M']:+.0f}|{r['buy_M']:.0f}|"
              f"{r['sell_M']:.0f}|{r['KOR_SECN_NM'][:32]}|")


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 2:
        start, end = args[0], args[1]
    else:
        start, end = this_week_mon_fri()
    print(f"=== 서학개미 주간 순매수 순위  {start} → {end}  (SEIBRO, USD, top-50 캡) ===")

    df = weekly_ranking(start, end)
    if df.empty:
        print("데이터 없음 (장 미개장 기간이거나 SEIBRO 응답 비어있음)")
        sys.exit(0)

    miss = df["ticker"].str.startswith("?").sum()
    print(f"종목 {len(df)}개 / 미해결 티커 {miss}개\n")
    print_netbuy_ranking(df)
