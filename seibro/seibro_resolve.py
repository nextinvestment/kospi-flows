"""ISIN → 티커 리졸버 (재사용 모듈).

우선순위: 캐시(isin_ticker_cache.json) → MANUAL(레버리지/인버스/신규 수동매핑)
          → EODHD /api/search/{isin} 라이브 검색(성공분은 캐시에 기록).
미해결은 '?종목명' 으로 표기해 절대 조용히 누락되지 않게 함.

다른 스크립트에서:
    from seibro_resolve import label_df
    df = label_df(df)        # df['ticker'] 컬럼 추가
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import requests

HERE = Path(__file__).parent
DATA = HERE / "data"
CACHE_F = DATA / "isin_ticker_cache.json"
sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY  # noqa: E402

CACHE = json.loads(CACHE_F.read_text(encoding="utf-8")) if CACHE_F.exists() else {}

# EODHD가 못 찾는 레버리지/인버스/신규 ETF 수동 매핑 (fix_quarterly_top10.py 와 동기화).
MANUAL = {
    "US25459W5408": "TMF",
    "US74347G4322": "SQQQ", "US74350P6759": "SQQQ",
    "US25460G3368": "SOXS", "US25460G1123": "SOXS", "US25461H5726": "SOXS",
    "US5494981039": "LCID",
    "US74347Y7638": "BOIL",
    "US92864M4006": "ETHU", "US92864M7983": "ETHU",
    "US92891H6062": "UVIX",
    "US25461A3876": "KORU",
    "JP3049130002": "TLT(JPYh)",
    "US26923Q5642": "BMNR·2xL",
    "US88636V8431": "IONQ·2xS",
    "US88636V6526": "RGTI·2xS",
    "US46092D3843": "TSLA·2xS",
    "US87975E7765": "SPACE",
    "US88636J4444": "TSLY",
    "US88634T4931": "MSTY",
    "US88636J2539": "MSTX",
    "US25461A5285": "MUU",
    # 2025~26 신규 단일종목 2배 레버리지 ETF (EODHD 미수록, 웹 확인)
    "US38747R5533": "INTW",          # GraniteShares 2x Long INTC
    "US46143U5424": "ASTX",          # Tradr 2x Long ASTS
    "US88340W5250": "SPCH",          # Leverage Shares 2x Long SPCX
    "US46152A6689": "SNXX",          # Tradr 2x Long SNDK
    "US46152A4296": "AAOX",          # Tradr 2x Long AAOI
    "HK0001205258": "7709(SKhy2x)",  # CSOP SK Hynix Daily 2x (홍콩 7709)
}

_US_EXCH = {"US", "NASDAQ", "NYSE", "BATS", "NYSE ARCA", "AMEX"}


def _eodhd_search(isin: str) -> str | None:
    try:
        r = requests.get(f"https://eodhd.com/api/search/{isin}",
                         params={"api_token": EODHD_API_KEY, "fmt": "json"}, timeout=20)
        res = r.json() if r.status_code == 200 else []
    except Exception:
        res = []
    us = [x for x in res if x.get("Exchange") in _US_EXCH]
    pick = us or res
    return pick[0]["Code"] if pick else None


def resolve(isin: str, name: str = "", *, live: bool = True) -> str:
    """ISIN → 표시 티커. 미해결이면 '?<name>'. live=True면 EODHD 검색까지 시도."""
    if isin in MANUAL:                       # 수동매핑이 캐시보다 우선(레버리지 정확도)
        return MANUAL[isin]
    cached = CACHE.get(isin)
    if cached:
        return cached.split(".")[0]
    if live and isin not in CACHE:            # 아직 안 찾아본 ISIN만 라이브 검색
        code = _eodhd_search(isin)
        full = f"{code}.US" if code else None
        CACHE[isin] = full
        if code:
            return code
    return "?" + str(name)[:16]


def save_cache():
    CACHE_F.write_text(json.dumps(CACHE, ensure_ascii=False, indent=2), encoding="utf-8")


def label_df(df, isin_col="ISIN", name_col="KOR_SECN_NM", out_col="ticker", *, live=True):
    """df에 out_col(티커) 컬럼 추가. 새로 해석한 ISIN은 캐시에 저장."""
    df = df.copy()
    df[out_col] = [resolve(r[isin_col], r.get(name_col, ""), live=live)
                   for _, r in df.iterrows()]
    if live:
        save_cache()
    return df
