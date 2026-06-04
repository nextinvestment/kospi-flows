# kospi-flows

KOSPI 투자자별 수급 분석 — 외국인·기관·개인 일별/월별 누적 + 워치리스트 종목별 추적. Naver Finance 스크래핑 기반 (KRX OTP가 세션 검증 강화로 헤드리스 호출에 403을 주기 때문).

## Entry points

| Command | What it does |
|---|---|
| `streamlit run app.py` | 대시보드 (5 탭: 오늘의 수급 / 일별·누적 / 종목별 / 종목 랭킹 / KOSPI200 proxy) |
| `python run_daily.py` | 증분 인제스트 (KOSPI 2pp + 종목 2pp ≈ 최근 40일) |
| `python run_daily.py backfill 60 10` | 백필 (KOSPI 60pp ≈ 2.5년 + 종목 10pp ≈ 200일) |
| `run_daily.bat` | 위의 daily, 로그 `data/daily_run_*.log` (Task Scheduler용) |

## Files

- `config.py` — `WATCHLIST` (코드→종목명 dict), `INVESTOR_COLS` (10개 투자주체), `KOSPI200_PROXY_CODE = "069500"`
- `fetcher.py` — Naver 스크래퍼. `fetch_market_page(market, page)`, `fetch_stock_page(code, page)`, 페이지 합치는 `fetch_market` / `fetch_stock`, 병렬 종목 `fetch_stocks_parallel`
- `store.py` — Parquet 저장 (`market_flows.parquet`, `stock_flows.parquet`). 날짜+코드 upsert 중복제거
- `run_daily.py` — daily / backfill 모드
- `app.py` — Streamlit 대시보드

## Data sources & units

| 데이터 | URL | 단위 |
|---|---|---|
| KOSPI 일별 투자자별 | `/sise/investorDealTrendDay.naver?sosok=` (KOSDAQ은 `sosok=1`) | **억원** |
| 종목별 외국인·기관 | `/item/frgn.naver?code=XXXXXX` | **주식수** (앱에서 종가 곱해 억원 환산) |
| 외국인 보유율 | 위 frgn.naver 페이지 | % |

Naver는 euc-kr 인코딩. `_get()`에서 강제 처리.

## 의도적 결정 / 한계

- **종목별 외국인 순매수 상위 랭킹**: Naver의 `sise_deal_rank.naver` 페이지는 JS 렌더라 정적 스크래핑 불가. 대신 `WATCHLIST` (시총 상위 20개)를 매일 일괄 호출 → 일별/누적 정렬. 더 넓게 보려면 `config.WATCHLIST`에 코드 추가.
- **KOSPI 200 선물 투자자별**: Naver에 별도 페이지 없음. KODEX 200 ETF (069500)의 외국인 매매를 proxy로 사용 (`Tab 5`).
- **pykrx 사용 안 함**: KRX OTP 엔드포인트가 세션 기반 검증을 강화해 헤드리스에서 403 / "LOGOUT" 응답. 향후 Selenium으로 세션 처리 가능하면 KRX 직접 호출이 더 정확.
- **종목별 데이터는 환산값**: 외국인 순매수량(주) × 종가 = 억원 환산. 동일일 평단가 ≠ 종가이므로 실제 거래금액과 약간 차이 있음 (대시보드 노출 시 "종가환산" 표기).

## Scheduling

`Daily KOSPI Flows Ingest` (Windows Task Scheduler, 매일 18:00 권장 — 한국장 마감 후) → `run_daily.bat`.
