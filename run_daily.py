"""Daily ingest: refresh KOSPI market flow + watchlist per-stock flow.

Pulls last few pages to cover any missed trading days. Idempotent via upsert.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

import fetcher
import store
from pathlib import Path
import pandas as pd
from config import WATCHLIST

HERE = Path(__file__).parent
UNIVERSE_CSV = HERE / "data" / "kospi_universe.csv"
UNIVERSE_REFRESH_DAYS = 7  # re-fetch market-cap ranking weekly


def get_codes() -> list[str]:
    """Universe.csv (top-200) if fresh, else refresh; fallback = WATCHLIST."""
    import time as _t
    if UNIVERSE_CSV.exists():
        age_days = (_t.time() - UNIVERSE_CSV.stat().st_mtime) / 86400
        if age_days < UNIVERSE_REFRESH_DAYS:
            df = pd.read_csv(UNIVERSE_CSV, dtype={"code": str})
            return df["code"].tolist()
    try:
        pairs = fetcher.fetch_kospi_universe(top_n=200)
        pd.DataFrame(pairs, columns=["code", "name"]).to_csv(UNIVERSE_CSV, index=False, encoding="utf-8")
        return [c for c, _ in pairs]
    except Exception as e:
        print(f"  ! universe refresh failed, falling back to WATCHLIST: {e}")
        return list(WATCHLIST.keys())


def ingest_market(market: str = "KOSPI", pages: int = 2) -> int:
    print(f"[{market}] fetching {pages} pages...")
    df = fetcher.fetch_market(market, pages=pages)
    if df.empty:
        print(f"[{market}] no data returned")
        return 0
    merged = store.upsert_market(df, market=market)
    new_rows = len(df)
    total = len(merged[merged["market"] == market]) if "market" in merged.columns else len(merged)
    print(f"[{market}] +{new_rows} rows (table now: {total} for {market}, latest={df['date'].max().date()})")
    return new_rows


def ingest_stocks(pages: int = 2) -> int:
    codes = get_codes()
    print(f"[stocks] fetching {len(codes)} tickers × {pages} pages...")
    df = fetcher.fetch_stocks_parallel(codes, pages=pages, max_workers=8)
    if df.empty:
        print("[stocks] no data returned")
        return 0
    merged = store.upsert_stocks(df)
    print(f"[stocks] +{len(df)} rows (table now: {len(merged)}, latest={df['date'].max().date()})")
    return len(df)


def main(market_pages: int = 2, stock_pages: int = 2):
    start = time.time()
    print(f"=== kospi-flows daily ingest @ {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    ingest_market("KOSPI", pages=market_pages)
    ingest_stocks(pages=stock_pages)
    print(f"=== done in {time.time() - start:.1f}s ===")


def backfill(market_pages: int = 60, stock_pages: int = 15):
    """One-off historical backfill. 60 pages ≈ 600 trading days ≈ 2.5 years."""
    print(f"=== BACKFILL: market={market_pages}pp, stocks={stock_pages}pp ===")
    ingest_market("KOSPI", pages=market_pages)
    ingest_stocks(pages=stock_pages)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        mp = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        sp = int(sys.argv[3]) if len(sys.argv) > 3 else 15
        backfill(mp, sp)
    else:
        main()
