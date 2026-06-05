"""Naver Finance scrapers for KOSPI investor flow data.

All amounts in 억원 (100M KRW) for market-level data.
Per-stock data is in shares (주) — caller multiplies by price for KRW.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import USER_AGENT, INVESTOR_COLS

BASE = "https://finance.naver.com"
HEADERS = {"User-Agent": USER_AGENT, "Referer": f"{BASE}/sise/"}


def _get(url: str, retries: int = 3, encoding: str = "euc-kr") -> str:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.encoding = encoding
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError("unreachable")


def _parse_num(s: str) -> float:
    """Convert '63,537' / '-63,035' / '+3,088,203' / '--' to float."""
    s = s.strip().replace(",", "").replace("+", "")
    if s in ("", "--", "-"):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _parse_date_2digit(s: str) -> pd.Timestamp | None:
    """'26.06.02' -> Timestamp('2026-06-02')."""
    s = s.strip()
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2})", s)
    if not m:
        return None
    yy, mm, dd = m.groups()
    year = 2000 + int(yy)
    return pd.Timestamp(year=year, month=int(mm), day=int(dd))


def _parse_date_4digit(s: str) -> pd.Timestamp | None:
    """'2026.06.02' -> Timestamp."""
    s = s.strip()
    m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})", s)
    if not m:
        return None
    y, mo, d = m.groups()
    return pd.Timestamp(year=int(y), month=int(mo), day=int(d))


# ---------------------------------------------------------------------------
# Market-wide investor flow (KOSPI / KOSDAQ)
# ---------------------------------------------------------------------------

def fetch_market_page(market: str = "KOSPI", page: int = 1, bizdate: str | None = None) -> pd.DataFrame:
    """Fetch one page (~10 trading days) of market-level investor flow.

    Columns returned: date, plus values in 억원 for each investor in INVESTOR_COLS.
    sosok="" for KOSPI on Naver, "1" for KOSDAQ.
    """
    sosok = "" if market.upper() == "KOSPI" else "1"
    if bizdate is None:
        bizdate = datetime.now().strftime("%Y%m%d")
    url = f"{BASE}/sise/investorDealTrendDay.naver?bizdate={bizdate}&sosok={sosok}&type=0&page={page}"
    html = _get(url)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="type_1")
    if table is None:
        return pd.DataFrame()
    rows = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 11:
            continue
        date = _parse_date_2digit(tds[0].get_text(strip=True))
        if date is None:
            continue
        vals = [_parse_num(td.get_text(strip=True)) for td in tds[1:11]]
        rows.append([date] + vals)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date"] + INVESTOR_COLS)
    return df


def fetch_market(market: str = "KOSPI", pages: int = 10, bizdate: str | None = None) -> pd.DataFrame:
    """Fetch N pages and concat. pages=10 ≈ ~100 trading days ≈ ~5 months."""
    frames = []
    for p in range(1, pages + 1):
        df = fetch_market_page(market, p, bizdate)
        if df.empty:
            break
        frames.append(df)
        time.sleep(0.15)  # be polite to Naver
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# Per-stock investor flow (frgn.naver)
# ---------------------------------------------------------------------------

def fetch_stock_page(code: str, page: int = 1) -> pd.DataFrame:
    """One page (~20 days) of per-stock institutional / foreign trading.

    Returns: date, close, change, ret_pct, volume, inst_net (shares),
             foreign_net (shares), foreign_holding (shares), foreign_pct.
    """
    url = f"{BASE}/item/frgn.naver?code={code}&page={page}"
    html = _get(url)
    soup = BeautifulSoup(html, "html.parser")
    # The data table follows the th block we saw earlier
    rows = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue
        date_txt = tds[0].get_text(strip=True)
        date = _parse_date_4digit(date_txt)
        if date is None:
            continue
        close = _parse_num(tds[1].get_text(strip=True))
        # tds[2] is 전일비 (price change) — strip leading 상/하 markers
        chg_text = tds[2].get_text(strip=True)
        chg = _parse_num(re.sub(r"[상하보합]", "", chg_text))
        ret_pct = _parse_num(tds[3].get_text(strip=True).rstrip("%"))
        volume = _parse_num(tds[4].get_text(strip=True))
        inst_net = _parse_num(tds[5].get_text(strip=True))
        foreign_net = _parse_num(tds[6].get_text(strip=True))
        foreign_hold = _parse_num(tds[7].get_text(strip=True))
        foreign_pct = _parse_num(tds[8].get_text(strip=True).rstrip("%"))
        rows.append([date, close, chg, ret_pct, volume, inst_net, foreign_net, foreign_hold, foreign_pct])
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        rows,
        columns=[
            "date", "close", "change", "ret_pct", "volume",
            "inst_net", "foreign_net", "foreign_hold", "foreign_pct",
        ],
    )


def fetch_stock(code: str, pages: int = 5) -> pd.DataFrame:
    """Multi-page per-stock fetch. pages=5 ≈ 100 trading days."""
    frames = []
    for p in range(1, pages + 1):
        df = fetch_stock_page(code, p)
        if df.empty:
            break
        frames.append(df)
        time.sleep(0.1)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["code"] = code
    out = out.drop_duplicates(subset=["date", "code"]).sort_values("date").reset_index(drop=True)
    return out


def fetch_index_page(code: str = "KOSPI", page: int = 1) -> pd.DataFrame:
    """One page (~10 trading days) of index OHLC. code: KOSPI, KOSDAQ, KPI200."""
    url = f"{BASE}/sise/sise_index_day.naver?code={code}&page={page}"
    html = _get(url)
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        date = _parse_date_4digit(tds[0].get_text(strip=True))
        if date is None:
            continue
        close = _parse_num(tds[1].get_text(strip=True))
        change = _parse_num(tds[2].get_text(strip=True))
        ret_txt = tds[3].get_text(strip=True).rstrip("%")
        ret_pct = _parse_num(ret_txt)
        if "−" in tds[3].get_text() or "-" in tds[3].get_text():
            ret_pct = -abs(ret_pct) if ret_pct == ret_pct else ret_pct  # NaN-safe
        volume = _parse_num(tds[4].get_text(strip=True))
        value = _parse_num(tds[5].get_text(strip=True))  # 백만 (million KRW)
        rows.append([date, close, change, ret_pct, volume, value])
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["date", "close", "change", "ret_pct", "volume_kshares", "value_mn"])


def fetch_index(code: str = "KOSPI", pages: int = 10) -> pd.DataFrame:
    frames = []
    for p in range(1, pages + 1):
        df = fetch_index_page(code, p)
        if df.empty:
            break
        df["index_code"] = code
        frames.append(df)
        time.sleep(0.15)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(subset=["date", "index_code"]).sort_values("date").reset_index(drop=True)


def fetch_kospi_universe(top_n: int = 200) -> list[tuple[str, str]]:
    """KOSPI market-cap top N codes from Naver. Returns [(code, name), ...].

    Naver sise_market_sum has 50 stocks/page; we hit ceil(top_n/50) pages.
    """
    import math
    pages = math.ceil(top_n / 50)
    seen: dict[str, str] = {}
    for page in range(1, pages + 1):
        url = f"{BASE}/sise/sise_market_sum.naver?sosok=0&page={page}"
        html = _get(url)
        soup = BeautifulSoup(html, "html.parser")
        tab = soup.find("table", class_="type_2")
        if tab is None:
            break
        for a in tab.find_all("a", href=True):
            if "code=" not in a["href"]:
                continue
            code = a["href"].split("code=")[-1]
            if not (code.isdigit() and len(code) == 6):
                continue
            name = a.get_text(strip=True)
            if not name:
                continue
            seen.setdefault(code, name)
            if len(seen) >= top_n:
                break
        if len(seen) >= top_n:
            break
        time.sleep(0.15)
    return list(seen.items())[:top_n]


def fetch_stocks_parallel(codes: list[str], pages: int = 5, max_workers: int = 8) -> pd.DataFrame:
    """Fan-out per-stock fetches, concat results."""
    frames = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fetch_stock, c, pages): c for c in codes}
        for fut in as_completed(futs):
            c = futs[fut]
            try:
                df = fut.result()
                if not df.empty:
                    frames.append(df)
            except Exception as e:
                print(f"  ! {c} failed: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(["date", "code"]).reset_index(drop=True)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== KOSPI 일별 투자자별 (page 1) ===")
    df = fetch_market_page("KOSPI", 1)
    print(df)
    print("\n=== 005930 삼성전자 (page 1) ===")
    df = fetch_stock_page("005930", 1)
    print(df.head())
