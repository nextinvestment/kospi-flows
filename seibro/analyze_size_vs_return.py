"""Does the SIZE of the SEIBRO pick (settlement amount, rank) predict 1M return?

Three views:
  1. Rank (RNUM 1-25): is #1 better than #25 on average?
  2. Quintile of settlement amount (within each month)
  3. Pearson + Spearman correlation of (settle_amt_usd, ret_pct)
  4. Same for NET BUY (signed): does heavy net-buy predict better return?
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
CSV = HERE / "data" / "seibro_backtest_stocks.csv"


def main():
    df = pd.read_csv(CSV)
    print(f"=== SEIBRO size↔return 분석 ({len(df)} 픽, {df['month'].nunique()}개월) ===\n")

    # --- 1. By RNUM (rank inside that month) ---
    print("--- (1) 순위(RNUM)별 평균 수익률 ---")
    by_rank = df.groupby("rnum").agg(
        n=("ret_pct", "count"),
        avg=("ret_pct", "mean"),
        median=("ret_pct", "median"),
        win=("ret_pct", lambda x: (x > 0).mean() * 100),
        alpha=("alpha_pp", "mean"),
    ).reset_index()
    print(by_rank.to_string(
        index=False,
        formatters={"avg": "{:+.2f}".format, "median": "{:+.2f}".format,
                   "win": "{:.0f}".format, "alpha": "{:+.2f}".format},
    ))

    # Top-5 vs Bot-5
    top5 = df[df["rnum"] <= 5]
    bot5 = df[df["rnum"] >= 21]
    print(f"\n  TOP5 (rank 1-5):   avg={top5['ret_pct'].mean():+.2f}%  alpha={top5['alpha_pp'].mean():+.2f}%p  n={len(top5)}")
    print(f"  BOT5 (rank 21-25): avg={bot5['ret_pct'].mean():+.2f}%  alpha={bot5['alpha_pp'].mean():+.2f}%p  n={len(bot5)}")

    # --- 2. By settlement-amount quintile (cross-section all months) ---
    print("\n--- (2) 결제금액 quintile별 평균 수익률 ---")
    df["q_amt"] = pd.qcut(df["settle_amt_usd"], 5, labels=["Q1(소액)", "Q2", "Q3", "Q4", "Q5(거액)"])
    by_q = df.groupby("q_amt", observed=True).agg(
        n=("ret_pct", "count"),
        avg=("ret_pct", "mean"),
        median=("ret_pct", "median"),
        win=("ret_pct", lambda x: (x > 0).mean() * 100),
        alpha=("alpha_pp", "mean"),
        amt_med=("settle_amt_usd", "median"),
    ).reset_index()
    print(by_q.to_string(
        index=False,
        formatters={"avg": "{:+.2f}".format, "median": "{:+.2f}".format,
                   "win": "{:.0f}".format, "alpha": "{:+.2f}".format,
                   "amt_med": "{:,.0f}".format},
    ))

    # --- 3. Correlation ---
    print("\n--- (3) 결제금액 vs 1M 수익률 상관계수 ---")
    p_corr = df[["settle_amt_usd", "ret_pct"]].corr(method="pearson").iloc[0, 1]
    s_corr = df[["settle_amt_usd", "ret_pct"]].corr(method="spearman").iloc[0, 1]
    print(f"  Pearson  (linear)  : {p_corr:+.4f}")
    print(f"  Spearman (rank)    : {s_corr:+.4f}")
    print(f"  → ~0 = no relationship; +0.1~0.2 = weak positive; >0.3 = meaningful")

    # --- 4. NET BUY (signed) ---
    print("\n--- (4) 순매수금액(signed) vs 1M 수익률 ---")
    print(f"  Pearson : {df[['net_buy_usd', 'ret_pct']].corr(method='pearson').iloc[0,1]:+.4f}")
    print(f"  Spearman: {df[['net_buy_usd', 'ret_pct']].corr(method='spearman').iloc[0,1]:+.4f}")
    # net buy > 0 vs < 0
    pos = df[df["net_buy_usd"] > 0]
    neg = df[df["net_buy_usd"] < 0]
    print(f"  순매수(+): avg={pos['ret_pct'].mean():+.2f}%  alpha={pos['alpha_pp'].mean():+.2f}%p  n={len(pos)}")
    print(f"  순매도(-): avg={neg['ret_pct'].mean():+.2f}%  alpha={neg['alpha_pp'].mean():+.2f}%p  n={len(neg)}")

    # --- 5. NET BUY ratio (net / total) — buying conviction ---
    print("\n--- (5) 순매수 비율 (net_buy / settle_amt) — 매수 우위 강도 ---")
    df["conv"] = df["net_buy_usd"] / df["settle_amt_usd"]
    df["q_conv"] = pd.qcut(df["conv"], 5, labels=["Q1(강한매도)", "Q2", "Q3", "Q4", "Q5(강한매수)"])
    by_conv = df.groupby("q_conv", observed=True).agg(
        n=("ret_pct", "count"),
        avg=("ret_pct", "mean"),
        win=("ret_pct", lambda x: (x > 0).mean() * 100),
        alpha=("alpha_pp", "mean"),
    ).reset_index()
    print(by_conv.to_string(
        index=False,
        formatters={"avg": "{:+.2f}".format, "win": "{:.0f}".format, "alpha": "{:+.2f}".format},
    ))


if __name__ == "__main__":
    main()
