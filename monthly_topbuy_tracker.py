"""Monthly foreign-buy TOP-10 picks → 1-month-forward return backtest.

For each calendar month with full coverage:
  1. Sum daily foreign net-buy (억원) per stock across that month
  2. TOP 10 by aggregate foreign buy
  3. Compute 1-month-forward return = (next month-end close / this month-end close - 1)
  4. Report per-pick + monthly avg/median + overall stats

Universe is whatever's in stock_flows.parquet (currently KOSPI top-200 by mcap).
Months with < 15 trading days at either end are skipped (partial-month bias).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent


def load_data():
    s = pd.read_parquet(HERE / "data" / "stock_flows.parquet")
    s["date"] = pd.to_datetime(s["date"])
    s["foreign_value"] = s["foreign_net"] * s["close"] / 1e8  # 억원
    s["month"] = s["date"].dt.to_period("M")
    uni_path = HERE / "data" / "kospi_universe.csv"
    if uni_path.exists():
        u = pd.read_csv(uni_path, dtype={"code": str})
        name_map = dict(zip(u["code"], u["name"]))
    else:
        name_map = {}
    return s, name_map


def month_end_close(s: pd.DataFrame) -> pd.DataFrame:
    """Last close per (code, month)."""
    return (
        s.sort_values("date")
        .groupby(["code", "month"])
        .agg(close=("close", "last"), days=("date", "nunique"))
        .reset_index()
    )


def run(top_n: int = 10, min_days: int = 15):
    s, name_map = load_data()
    full_months = (
        s.groupby("month")["date"].nunique().reset_index(name="days")
    )
    full_months = full_months[full_months["days"] >= min_days]["month"].tolist()
    if len(full_months) < 2:
        print("Not enough full months in dataset.")
        return

    monthly_buy = (
        s[s["month"].isin(full_months)]
        .groupby(["month", "code"])["foreign_value"]
        .sum()
        .reset_index()
    )
    closes = month_end_close(s)

    rows = []
    for i, m in enumerate(full_months[:-1]):
        next_m = full_months[i + 1]
        top = monthly_buy[monthly_buy["month"] == m].nlargest(top_n, "foreign_value")
        for _, r in top.iterrows():
            code = r["code"]
            c_now = closes[(closes["code"] == code) & (closes["month"] == m)]
            c_next = closes[(closes["code"] == code) & (closes["month"] == next_m)]
            if c_now.empty or c_next.empty:
                continue
            p0 = float(c_now["close"].iloc[0])
            p1 = float(c_next["close"].iloc[0])
            ret = (p1 / p0 - 1) * 100
            rows.append({
                "월": str(m),
                "rank": 1,  # filled below
                "종목": name_map.get(code, code),
                "코드": code,
                "외국인매수(억)": r["foreign_value"],
                "월말종가": p0,
                "익월말종가": p1,
                "1M수익률(%)": ret,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        print("No picks generated.")
        return

    df["rank"] = df.groupby("월")["외국인매수(억)"].rank(ascending=False, method="first").astype(int)
    df = df.sort_values(["월", "rank"]).reset_index(drop=True)

    print(f"=== 월별 외국인 매수 TOP {top_n} → 1달 후 수익률 ===")
    print(f"(universe: {s['code'].nunique()}개 종목, full month = {min_days}+ 거래일)\n")
    for m, g in df.groupby("월"):
        avg_ret = g["1M수익률(%)"].mean()
        win = (g["1M수익률(%)"] > 0).sum()
        print(f"--- {m} (TOP{top_n} → 평균 {avg_ret:+.2f}%, 승률 {win}/{len(g)}) ---")
        print(g[["rank", "종목", "외국인매수(억)", "월말종가", "익월말종가", "1M수익률(%)"]]
              .to_string(index=False,
                         formatters={
                             "외국인매수(억)": "{:+,.0f}".format,
                             "월말종가": "{:,.0f}".format,
                             "익월말종가": "{:,.0f}".format,
                             "1M수익률(%)": "{:+.2f}".format,
                         }))
        print()

    # Overall
    print("=== Overall ===")
    print(f"총 픽 수: {len(df)}")
    print(f"평균 1M 수익률: {df['1M수익률(%)'].mean():+.2f}%")
    print(f"중앙값:        {df['1M수익률(%)'].median():+.2f}%")
    print(f"승률 (> 0%):    {(df['1M수익률(%)'] > 0).mean() * 100:.1f}% ({(df['1M수익률(%)'] > 0).sum()}/{len(df)})")
    print(f"최대 +수익:    {df['1M수익률(%)'].max():+.2f}% ({df.loc[df['1M수익률(%)'].idxmax(), '종목']}, {df.loc[df['1M수익률(%)'].idxmax(), '월']})")
    print(f"최대 -수익:    {df['1M수익률(%)'].min():+.2f}% ({df.loc[df['1M수익률(%)'].idxmin(), '종목']}, {df.loc[df['1M수익률(%)'].idxmin(), '월']})")

    # Compare to KOSPI index over same months
    idx_path = HERE / "data" / "kospi_index.parquet"
    if idx_path.exists():
        idx = pd.read_parquet(idx_path)
        idx = idx[idx["index_code"] == "KOSPI"].copy()
        idx["date"] = pd.to_datetime(idx["date"])
        idx["month"] = idx["date"].dt.to_period("M")
        idx_close = idx.sort_values("date").groupby("month")["close"].last().reset_index()
        idx_rets = []
        for i in range(len(full_months) - 1):
            m, nm = full_months[i], full_months[i + 1]
            try:
                p0 = idx_close[idx_close["month"] == m]["close"].iloc[0]
                p1 = idx_close[idx_close["month"] == nm]["close"].iloc[0]
                idx_rets.append((p1 / p0 - 1) * 100)
            except IndexError:
                pass
        if idx_rets:
            avg_idx = sum(idx_rets) / len(idx_rets)
            print(f"\n같은 기간 KOSPI 평균 월수익률: {avg_idx:+.2f}%")
            print(f"전략 vs KOSPI alpha:           {df['1M수익률(%)'].mean() - avg_idx:+.2f}%p")

    # Save CSV
    out_csv = HERE / "data" / "monthly_topbuy_tracking.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {out_csv}")


if __name__ == "__main__":
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    run(top_n=top_n)
