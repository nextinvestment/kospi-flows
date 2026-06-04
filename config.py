"""Configuration: stock universe + display names."""
from __future__ import annotations

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

WATCHLIST: dict[str, str] = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "069500": "KODEX 200",
    "005380": "현대차",
    "035420": "NAVER",
    "035720": "카카오",
    "207940": "삼성바이오로직스",
    "051910": "LG화학",
    "006400": "삼성SDI",
    "068270": "셀트리온",
    "028260": "삼성물산",
    "012330": "현대모비스",
    "105560": "KB금융",
    "055550": "신한지주",
    "017670": "SK텔레콤",
    "066570": "LG전자",
    "003670": "포스코퓨처엠",
    "096770": "SK이노베이션",
    "032830": "삼성생명",
    "015760": "한국전력",
}

KOSPI200_PROXY_CODE = "069500"
KOSPI200_PROXY_NAME = "KODEX 200 (코스피200 선물 proxy)"

INVESTOR_COLS = [
    "개인",
    "외국인",
    "기관계",
    "금융투자",
    "보험",
    "투신",
    "은행",
    "기타금융",
    "연기금등",
    "기타법인",
]
