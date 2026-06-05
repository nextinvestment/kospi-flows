"""Backtest grid: monthly foreign TOP-K picks × multiple holding horizons × buy/sell direction.

For each calendar month with full coverage:
  - direction='buy': pick TOP-K by aggregate monthly foreign net-buy
  - direction='sell': pick BOTTOM-K (largest net-sell) — short simulation
  - holding_days ∈ {5, 20, 60} business days from the month-end entry

Entry  = close of month-end trading day
Exit   = close N trading days later (forward-fill if no data)
Return = exit / entry - 1     (for buy)
       = entry / exit - 1     (for sell, i.e. short return)

Output: per-month table + grid summary (avg, median, win-rate, alpha vs KOSPI).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent

HORIZONS = {"1주(5bd)": 5, "1개월(20bd)": 20, "3개월(60bd)": 60}


def load_data():
    s = pd.read_parquet(HERE / "data" / "stock_flows.parquet")
    s["date"] = pd.to_datetime(s["date"])
    s["foreign_value"] = s["foreign_net"] * s["close"] / 1e8
    s["month"] = s["date"].dt.to_period("M")
    u = pd.read_csv(HERE / "data" / "kospi_universe.csv", dtype={"code": str})
    return s, dict(zip(u["code"], u["name"]))


def trading_days(s: pd.DataFrame) -> list[pd.Timestamp]:
    return sorted(s["date"].unique())


def month_end_trading_day(s: pd.DataFrame) -> dict:
    """Per period → last trading day in that month."""
    return s.sort_values("date").groupby("month")["date"].last().to_dict()


def close_on(s: pd.DataFrame, code: str, d: pd.Timestamp) -> float | None:
    rows = s[(s["code"] == code) & (s["date"] == d)]
    if rows.empty:
        return None
    return float(rows["close"].iloc[0])


def kospi_returns(horizon_bd: int):
    idx_path = HERE / "data" / "kospi_index.parquet"
    if not idx_path.exists():
        return {}
    idx = pd.read_parquet(idx_path)
    idx = idx[idx["index_code"] == "KOSPI"].copy()
    idx["date"] = pd.to_datetime(idx["date"])
    idx = idx.sort_values("date").reset_index(drop=True)
    out = {}
    for i, row in idx.iterrows():
        future_i = i + horizon_bd
        if future_i >= len(idx):
            break
        out[row["date"]] = (idx.loc[future_i, "close"] / row["close"] - 1) * 100
    return out


def run_grid(top_k: int = 10, min_days: int = 15):
    s, name_map = load_data()

    full_months = (
        s.groupby("month")["date"].nunique()
        .reset_index(name="days")
        .query("days >= @min_days")["month"]
        .tolist()
    )
    me_day = month_end_trading_day(s)
    bdays = trading_days(s)
    bday_idx = {d: i for i, d in enumerate(bdays)}

    # Pre-aggregate monthly foreign net by code
    monthly = (
        s[s["month"].isin(full_months)]
        .groupby(["month", "code"])["foreign_value"]
        .sum()
        .reset_index()
    )

    summary_rows = []

    for direction in ["buy", "sell"]:
        for label, horizon in HORIZONS.items():
            kospi_ret_map = kospi_returns(horizon)
            picks = []
            for m in full_months:
                month_df = monthly[monthly["month"] == m]
                if direction == "buy":
                    chosen = month_df.nlargest(top_k, "foreign_value")
                else:
                    chosen = month_df.nsmallest(top_k, "foreign_value")
                entry_day = me_day[m]
                ei = bday_idx.get(entry_day)
                if ei is None or ei + horizon >= len(bdays):
                    continue
                exit_day = bdays[ei + horizon]
                for _, r in chosen.iterrows():
                    p0 = close_on(s, r["code"], entry_day)
                    p1 = close_on(s, r["code"], exit_day)
                    if p0 is None or p1 is None:
                        continue
                    raw_ret = (p1 / p0 - 1) * 100
                    strat_ret = raw_ret if direction == "buy" else -raw_ret
                    picks.append({
                        "month": str(m),
                        "code": r["code"],
                        "name": name_map.get(r["code"], r["code"]),
                        "foreign_value": r["foreign_value"],
                        "entry": p0,
                        "exit": p1,
                        "raw_ret_pct": raw_ret,
                        "strat_ret_pct": strat_ret,
                        "kospi_ret_pct": kospi_ret_map.get(entry_day),
                    })
            if not picks:
                continue
            df = pd.DataFrame(picks)
            df["alpha"] = df["strat_ret_pct"] - df["kospi_ret_pct"].fillna(0)
            summary_rows.append({
                "direction": direction,
                "horizon": label,
                "picks": len(df),
                "avg_ret%": df["strat_ret_pct"].mean(),
                "median%": df["strat_ret_pct"].median(),
                "win%": (df["strat_ret_pct"] > 0).mean() * 100,
                "avg_kospi%": df["kospi_ret_pct"].mean(),
                "alpha%p": df["alpha"].mean(),
                "best": f"{df.loc[df['strat_ret_pct'].idxmax(), 'name']} {df['strat_ret_pct'].max():+.1f}%",
                "worst": f"{df.loc[df['strat_ret_pct'].idxmin(), 'name']} {df['strat_ret_pct'].min():+.1f}%",
            })

    sm = pd.DataFrame(summary_rows)
    print(f"\n=== Grid: TOP {top_k} 픽 × 2방향 × 3보유기간 (universe: KOSPI 시총상위 195) ===\n")
    pd.set_option("display.unicode.east_asian_width", True)
    print(sm.to_string(
        index=False,
        formatters={
            "avg_ret%": "{:+.2f}".format, "median%": "{:+.2f}".format,
            "win%": "{:.1f}".format, "avg_kospi%": "{:+.2f}".format,
            "alpha%p": "{:+.2f}".format,
        },
    ))

    print("\n해석 가이드:")
    print("- alpha%p > 0  : KOSPI 대비 초과수익. 외국인 신호 유효.")
    print("- direction='sell' & alpha > 0 : 외국인 매도 종목 short하면 KOSPI보다 나음.")
    print("- 가장 좋은 조합이 보유기간·방향 둘 다 알려줌.")

    # Save CSV
    out = HERE / "data" / "backtest_grid.csv"
    sm.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    top_k = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    run_grid(top_k=top_k)
