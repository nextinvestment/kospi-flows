"""올해(YTD) 월별 서학개미 순매수/순매도 TOP10 — 라이브 SEIBRO.

각 달을 fetch_top(월초, 월말) 으로 서버집계(결제금액 top-50) → 티커라벨 →
순매수 내림/오름 TOP10. 마지막 달은 오늘까지의 부분월.
사용: python seibro_ytd_monthly_top10.py [YEAR]
"""
from __future__ import annotations
import sys
import calendar
from datetime import date

import seibro_fetcher as sf
from seibro_resolve import label_df

sys.stdout.reconfigure(encoding="utf-8")


def month_table(y: int, m: int, today: date, top: int = 10):
    start = date(y, m, 1)
    last = date(y, m, calendar.monthrange(y, m)[1])
    end = min(last, today)
    partial = end < last
    hdr = f"### {y}-{m:02d}" + (f" (1일~{end.day}일, 진행중)" if partial else "")
    print(hdr)

    df = sf.fetch_top(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), top_n=50)
    if df.empty:
        print("  (데이터 없음)\n")
        return
    df = label_df(df)
    df["net_M"] = df["SUM_FRSEC_NET_BUY_AMT"] / 1e6
    buys = df.sort_values("net_M", ascending=False).head(top).reset_index(drop=True)
    sells = df.sort_values("net_M", ascending=True).head(top).reset_index(drop=True)
    print("|#|순매수|$M|↔|순매도|$M|")
    print("|-:|-|-:|-|-|-:|")
    for i in range(min(top, len(buys), len(sells))):
        b, s = buys.iloc[i], sells.iloc[i]
        print(f"|{i+1}|{b['ticker']}|{b['net_M']:+,.0f}| |"
              f"{s['ticker']}|{s['net_M']:+,.0f}|")
    print()


if __name__ == "__main__":
    today = date.today()
    year = int(sys.argv[1]) if len(sys.argv) > 1 else today.year
    last_m = today.month if year == today.year else 12
    for m in range(1, last_m + 1):
        month_table(year, m, today)
