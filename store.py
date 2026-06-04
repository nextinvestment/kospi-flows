"""Parquet persistence with date-based upsert dedup."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

MARKET_PATH = DATA_DIR / "market_flows.parquet"   # KOSPI / KOSDAQ daily investor flow
STOCK_PATH = DATA_DIR / "stock_flows.parquet"     # per-stock daily flow


def _upsert(path: Path, new: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if new.empty:
        return load(path)
    if path.exists():
        old = pd.read_parquet(path)
        combined = pd.concat([old, new], ignore_index=True)
    else:
        combined = new.copy()
    combined = combined.drop_duplicates(subset=keys, keep="last").sort_values(keys).reset_index(drop=True)
    combined.to_parquet(path, index=False)
    return combined


def load(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def upsert_market(df: pd.DataFrame, market: str = "KOSPI") -> pd.DataFrame:
    if df.empty:
        return load(MARKET_PATH)
    df = df.copy()
    df["market"] = market
    return _upsert(MARKET_PATH, df, ["date", "market"])


def upsert_stocks(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return load(STOCK_PATH)
    return _upsert(STOCK_PATH, df, ["date", "code"])


def load_market(market: str | None = None) -> pd.DataFrame:
    df = load(MARKET_PATH)
    if df.empty:
        return df
    if market is not None:
        df = df[df["market"] == market]
    return df.sort_values("date").reset_index(drop=True)


def load_stocks(code: str | None = None) -> pd.DataFrame:
    df = load(STOCK_PATH)
    if df.empty:
        return df
    if code is not None:
        df = df[df["code"] == code]
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def latest_date(path: Path) -> pd.Timestamp | None:
    df = load(path)
    if df.empty or "date" not in df.columns:
        return None
    return df["date"].max()
