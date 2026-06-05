"""Pure analysis functions over the parquet data.

No I/O — caller passes DataFrames in. Used by both push_and_notify.py and app.py.
"""
from __future__ import annotations

import pandas as pd


def add_value_cols(stocks: pd.DataFrame) -> pd.DataFrame:
    """Add foreign_value / inst_value (억원, signed) to per-stock DataFrame."""
    out = stocks.copy()
    out["foreign_value"] = out["foreign_net"] * out["close"] / 1e8
    out["inst_value"] = out["inst_net"] * out["close"] / 1e8
    return out


def n_day_cumulative_top(stocks: pd.DataFrame, n_days: int, top_k: int = 15,
                         name_map: dict[str, str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """N-day cumulative foreign net-value TOP-K (buy / sell).

    Returns (top_buy, top_sell) DataFrames with: name, code, cum_foreign(억), cum_inst(억), days_traded.
    """
    if stocks.empty:
        return pd.DataFrame(), pd.DataFrame()
    s = add_value_cols(stocks)
    last = s["date"].max()
    window = sorted(s["date"].unique())[-n_days:]
    w = s[s["date"].isin(window)]
    agg = (
        w.groupby("code")
        .agg(
            cum_foreign=("foreign_value", "sum"),
            cum_inst=("inst_value", "sum"),
            days_traded=("date", "nunique"),
        )
        .reset_index()
    )
    if name_map is not None:
        agg["name"] = agg["code"].map(name_map).fillna(agg["code"])
    else:
        agg["name"] = agg["code"]
    cols = ["name", "code", "cum_foreign", "cum_inst", "days_traded"]
    top_buy = agg.nlargest(top_k, "cum_foreign")[cols].reset_index(drop=True)
    top_sell = agg.nsmallest(top_k, "cum_foreign")[cols].reset_index(drop=True)
    return top_buy, top_sell


def consecutive_streak(stocks: pd.DataFrame, min_days: int = 5,
                       direction: str = "buy", name_map: dict[str, str] | None = None) -> pd.DataFrame:
    """Stocks with `min_days` consecutive same-direction foreign net trades ending today.

    direction: 'buy' (foreign_net > 0) or 'sell' (foreign_net < 0).
    """
    if stocks.empty:
        return pd.DataFrame()
    s = stocks.sort_values(["code", "date"])
    sign = 1 if direction == "buy" else -1
    s = s.assign(sign=(s["foreign_net"] * sign > 0).astype(int))

    results = []
    last_date = s["date"].max()
    for code, g in s.groupby("code"):
        g = g.sort_values("date")
        # streak length ending on last_date
        tail = g.tail(min_days)
        if len(tail) < min_days:
            continue
        if tail["date"].max() != last_date:
            continue
        if int(tail["sign"].sum()) != min_days:
            continue
        # extend streak backwards to find true length
        streak = 0
        for v in g["sign"].values[::-1]:
            if v == 1:
                streak += 1
            else:
                break
        cum_value = (g.tail(streak)["foreign_net"] * g.tail(streak)["close"]).sum() / 1e8
        results.append({
            "code": code,
            "name": (name_map or {}).get(code, code),
            "streak_days": streak,
            "cum_foreign_value": cum_value,
        })
    df = pd.DataFrame(results)
    if df.empty:
        return df
    sort_key = "cum_foreign_value"
    asc = direction == "sell"
    return df.sort_values(["streak_days", sort_key], ascending=[False, asc]).reset_index(drop=True)


def co_buying_selling(stocks: pd.DataFrame, top_k: int = 10,
                      name_map: dict[str, str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Latest-day stocks where foreign AND institutions both bought (or both sold).

    Returns (co_buy, co_sell). Sort by combined absolute value.
    """
    if stocks.empty:
        return pd.DataFrame(), pd.DataFrame()
    s = add_value_cols(stocks)
    last = s["date"].max()
    day = s[s["date"] == last].copy()
    if name_map is not None:
        day["name"] = day["code"].map(name_map).fillna(day["code"])
    else:
        day["name"] = day["code"]
    day["combined"] = day["foreign_value"] + day["inst_value"]
    co_buy = day[(day["foreign_value"] > 0) & (day["inst_value"] > 0)].copy()
    co_sell = day[(day["foreign_value"] < 0) & (day["inst_value"] < 0)].copy()
    cols = ["name", "code", "close", "ret_pct", "foreign_value", "inst_value", "combined"]
    return (
        co_buy.nlargest(top_k, "combined")[cols].reset_index(drop=True),
        co_sell.nsmallest(top_k, "combined")[cols].reset_index(drop=True),
    )


def divergence_check(market: pd.DataFrame, index: pd.DataFrame, window: int = 20) -> dict:
    """Compare foreign cumulative net flow vs KOSPI index over `window` days.

    Returns dict with: index_change_pct, foreign_cum, divergence ('bull'/'bear'/'aligned'), msg.
    """
    if market.empty or index.empty:
        return {"available": False}
    m = market[market["market"] == "KOSPI"].sort_values("date").tail(window)
    i = index.sort_values("date").tail(window)
    if len(m) < 2 or len(i) < 2:
        return {"available": False}
    idx_start = i.iloc[0]["close"]
    idx_end = i.iloc[-1]["close"]
    idx_pct = (idx_end / idx_start - 1) * 100
    foreign_cum = m["외국인"].sum()

    if idx_pct > 0 and foreign_cum < 0:
        verdict = "bear_divergence"
        msg = f"⚠️ <b>Bear Divergence</b>: KOSPI {idx_pct:+.2f}% 상승했지만 외국인 누적 {foreign_cum:+,.0f}억 순매도"
    elif idx_pct < 0 and foreign_cum > 0:
        verdict = "bull_divergence"
        msg = f"💡 <b>Bull Divergence</b>: KOSPI {idx_pct:+.2f}% 하락했지만 외국인 누적 {foreign_cum:+,.0f}억 순매수"
    else:
        verdict = "aligned"
        msg = f"KOSPI {idx_pct:+.2f}% · 외국인 누적 {foreign_cum:+,.0f}억 (방향 일치)"
    return {
        "available": True,
        "window": window,
        "index_pct": idx_pct,
        "foreign_cum": foreign_cum,
        "verdict": verdict,
        "msg": msg,
    }
