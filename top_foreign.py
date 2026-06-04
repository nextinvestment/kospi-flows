"""Foreign net-buy / net-sell TOP-N across KOSPI market-cap top universe.

Usage: python top_foreign.py [date] [N] [universe_size]
  date: YYYY-MM-DD (default = latest stored date)
  N:    rows per side (default 15)
  universe_size: how many top market-cap stocks to scan (default 200)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

import fetcher
import store

HERE = Path(__file__).parent
UNIVERSE_CSV = HERE / "data" / "kospi_universe.csv"


def refresh_universe(top_n: int = 200) -> dict[str, str]:
    print(f"Fetching KOSPI top-{top_n} universe from Naver…")
    pairs = fetcher.fetch_kospi_universe(top_n=top_n)
    df = pd.DataFrame(pairs, columns=["code", "name"])
    df.to_csv(UNIVERSE_CSV, index=False, encoding="utf-8")
    print(f"  saved {len(df)} → {UNIVERSE_CSV.name}")
    return dict(pairs)


def load_universe(top_n: int) -> dict[str, str]:
    if UNIVERSE_CSV.exists():
        df = pd.read_csv(UNIVERSE_CSV, dtype={"code": str})
        if len(df) >= top_n:
            return dict(zip(df["code"], df["name"]))
    return refresh_universe(top_n)


def fetch_for_universe(universe: dict[str, str], pages: int = 2) -> pd.DataFrame:
    codes = list(universe.keys())
    print(f"Fetching frgn.naver × {len(codes)} stocks × {pages} pages…")
    t0 = time.time()
    df = fetcher.fetch_stocks_parallel(codes, pages=pages, max_workers=8)
    print(f"  done in {time.time() - t0:.1f}s — {len(df)} rows")
    if df.empty:
        return df
    # Upsert into stock store so this also enriches the dashboard
    store.upsert_stocks(df)
    return df


def show_top(df: pd.DataFrame, universe: dict[str, str], date_str: str | None, n: int) -> None:
    if df.empty:
        print("(no data)")
        return
    if date_str:
        d = pd.Timestamp(date_str)
    else:
        d = df["date"].max()
    day = df[df["date"] == d].copy()
    if day.empty:
        print(f"No data on {d.date()}. Latest available: {df['date'].max().date()}")
        return
    day["name"] = day["code"].map(universe).fillna(day["code"])
    day["foreign_value"] = day["foreign_net"] * day["close"] / 1e8  # 억원
    day["inst_value"] = day["inst_net"] * day["close"] / 1e8

    top = day.nlargest(n, "foreign_value")[["name", "code", "close", "ret_pct", "foreign_net", "foreign_value", "inst_value"]]
    bot = day.nsmallest(n, "foreign_value")[["name", "code", "close", "ret_pct", "foreign_net", "foreign_value", "inst_value"]]

    fmt = "{rank:>2}. {name:<14} ({code})  종가 {close:>9,.0f}  {ret:>+6.2f}%  외국인 {fv:>+10,.0f}억  기관 {iv:>+8,.0f}억"
    print(f"\n=== {d.date()} KOSPI 시총상위 {len(day)}종목 중 외국인 순매수 TOP {n} ===")
    for i, r in enumerate(top.itertuples(index=False), 1):
        print(fmt.format(rank=i, name=r.name, code=r.code, close=r.close, ret=r.ret_pct, fv=r.foreign_value, iv=r.inst_value))

    print(f"\n=== {d.date()} 외국인 순매도 TOP {n} ===")
    for i, r in enumerate(bot.itertuples(index=False), 1):
        print(fmt.format(rank=i, name=r.name, code=r.code, close=r.close, ret=r.ret_pct, fv=r.foreign_value, iv=r.inst_value))


def main():
    args = sys.argv[1:]
    date_str = args[0] if len(args) > 0 and "-" in args[0] else None
    n = int(args[1]) if len(args) > 1 else 15
    universe_n = int(args[2]) if len(args) > 2 else 200

    universe = load_universe(universe_n)
    df = fetch_for_universe(universe, pages=2)
    show_top(df, universe, date_str, n)


if __name__ == "__main__":
    main()
