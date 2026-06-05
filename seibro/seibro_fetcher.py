"""Fetch Korean retail investor's foreign-stock settlement TOP-N per month from SEIBRO.

API: https://seibro.or.kr/websquare/engine/proworks/callServletService.jsp
Action: getImptFrcurStkSetlAmtList
Returns: per-stock aggregated settlement (buy + sell) in USD for the date range.

Sort options (S_TYPE):
  1 = ?? (unknown)
  2 = by 결제금액 (total settlement = buy + sell)   ← what we use
Direction (D_TYPE): 1 = desc

Country (S_COUNTRY): "ALL" or specific country code
"""
from __future__ import annotations

import re
import sys
import time
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

URL = "https://seibro.or.kr/websquare/engine/proworks/callServletService.jsp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Content-Type": "application/xml; charset=UTF-8",
    "Referer": "https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/ovsSec/BIP_CNTS10013V.xml&menuNo=921",
}


def fetch_top(start_date: str, end_date: str, top_n: int = 25, country: str = "ALL") -> pd.DataFrame:
    """One API call. start_date / end_date in YYYYMMDD format."""
    xml = (
        '<reqParam action="getImptFrcurStkSetlAmtList" '
        'task="ksd.safe.bip.cnts.OvsSec.process.OvsSecIsinPTask">'
        '<MENU_NO value="921"/>'
        '<CMM_BTN_ABBR_NM value="total_search,openall,print,hwp,word,pdf,seach,"/>'
        '<W2XPATH value="/IPORTAL/user/ovsSec/BIP_CNTS10013V.xml"/>'
        f'<PG_START value="1"/>'
        f'<PG_END value="{top_n}"/>'
        f'<START_DT value="{start_date}"/>'
        f'<END_DT value="{end_date}"/>'
        '<S_TYPE value="2"/>'   # sort by 결제금액
        f'<S_COUNTRY value="{country}"/>'
        '<D_TYPE value="1"/>'  # desc
        '</reqParam>'
    )
    r = requests.post(URL, data=xml.encode("utf-8"), headers=HEADERS, timeout=30)
    r.raise_for_status()
    return _parse(r.text)


def _parse(xml_text: str) -> pd.DataFrame:
    root = ET.fromstring(xml_text)
    rows = []
    for data in root.findall("data"):
        result = data.find("result")
        if result is None:
            continue
        rec = {}
        for child in result:
            v = child.get("value")
            rec[child.tag] = v
        rows.append(rec)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # convert numeric cols (USD)
    for c in ("SUM_FRSEC_BUY_AMT", "SUM_FRSEC_SELL_AMT", "SUM_FRSEC_TOT_AMT", "SUM_FRSEC_NET_BUY_AMT"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "RNUM" in df.columns:
        df["RNUM"] = pd.to_numeric(df["RNUM"], errors="coerce").astype("Int64")
    return df


def month_range(start_ym: str, end_ym: str) -> list[tuple[str, str, str]]:
    """List of (yyyymm, start_yyyymmdd, end_yyyymmdd) for each month in [start_ym, end_ym]."""
    out = []
    cur = pd.Period(start_ym, freq="M")
    end = pd.Period(end_ym, freq="M")
    while cur <= end:
        s = cur.start_time.strftime("%Y%m%d")
        e = cur.end_time.strftime("%Y%m%d")
        out.append((str(cur), s, e))
        cur += 1
    return out


def fetch_monthly_range(start_ym: str, end_ym: str, top_n: int = 25,
                       country: str = "ALL", sleep: float = 0.5) -> pd.DataFrame:
    """Fetch TOP-N for each month, concat with a 'month' column."""
    frames = []
    for ym, s, e in month_range(start_ym, end_ym):
        print(f"  fetching {ym} ({s}→{e})…", end=" ", flush=True)
        try:
            df = fetch_top(s, e, top_n=top_n, country=country)
        except Exception as ex:
            print(f"FAILED: {ex}")
            continue
        if df.empty:
            print("(empty)")
            continue
        df["month"] = ym
        frames.append(df)
        print(f"{len(df)} rows")
        time.sleep(sleep)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    start_ym = args[0] if len(args) > 0 else "2024-01"
    end_ym = args[1] if len(args) > 1 else date.today().strftime("%Y-%m")
    top_n = int(args[2]) if len(args) > 2 else 25
    country = args[3] if len(args) > 3 else "ALL"

    print(f"=== SEIBRO monthly TOP{top_n} settlement, {country}: {start_ym} → {end_ym} ===")
    df = fetch_monthly_range(start_ym, end_ym, top_n=top_n, country=country)
    out = Path(__file__).parent / "data"
    out.mkdir(exist_ok=True)
    csv_path = out / f"seibro_monthly_top{top_n}_{country.lower()}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nsaved: {csv_path}  ({len(df)} rows, {df['month'].nunique() if not df.empty else 0} months)")
    if not df.empty:
        latest = df[df["month"] == df["month"].max()].nlargest(5, "SUM_FRSEC_TOT_AMT")
        print(f"\nlatest month ({df['month'].max()}) TOP 5:")
        print(latest[["RNUM", "KOR_SECN_NM", "SUM_FRSEC_TOT_AMT", "SUM_FRSEC_NET_BUY_AMT"]].to_string(index=False))
