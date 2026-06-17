# 서학개미(한국 개인의 해외주식) 순매수/매도 TOP10 성과 분석 — 검증용 보고서

작성: Claude / 분석기간 데이터 기준일 2026-06-17
목적: **외부 검토자(GPT 등)가 API·키 없이 동봉 CSV만으로 모든 수치를 독립 재현·검증**하도록 함.

---

## 0. 한 줄 결론 (검증 대상)
1. 서학개미 **순매수 TOP10**과 **순매도 TOP10** 둘 다 SPY를 크게 이긴다(둘 다 테크 고베타라 강세장 베타 효과).
2. 그러나 **매수−매도 스프레드는 전 구간 음수**(6M −9.7%p, **1Y −20.5%p**) → 그들이 *판* 종목이 *산* 종목보다 더 올랐다 = 매수추종 신호는 무효, 오히려 역발상(그들의 매도종목 추종)이 우월.
3. 데뷔(첫 순매수상위 등장) 추적: **2023년 바닥 데뷔조 +300~1500%, 2025년 고점 데뷔조 −70~100% 손실** → 타이밍(사이클)이 종목보다 중요. 데뷔 직후 3개월은 대박주조차 약세.

> **정합성 주의**: 본 §4 수치는 모두 동봉 `prices_monthly.csv`에서 `recompute_canonical.py`로 재생성한 캐노니컬 값입니다(원천 단일화). 분석 중 사용한 ad-hoc 실행값과 1~19%p 차이가 있었으며(가격 fetch 시점·티커캐시 차이), **검증자는 동봉 파일 기준 값으로만 대조**하면 됩니다. 결론의 방향(매도>매수)은 정정 후 오히려 강화됨.

---

## 1. 데이터 출처
- **SEIBRO (한국예탁결제원, seibro.or.kr)** — 외화증권 월별 결제(보관)금액 상위. 액션 `getImptFrcurStkSetlAmtList`, 정렬=결제금액(buy+sell) 내림차순 TOP25. 컬럼: 매수금액/매도금액/총결제/**순매수(SUM_FRSEC_NET_BUY_AMT)**, 단위 **USD**. (스크래퍼: `seibro_fetcher.py`)
- **EODHD** — `adjusted_close`(분할·배당 보정). 가격은 종목 상장통화(대부분 USD).

> ⚠️ 핵심 한계 1: **유니버스 = "결제금액(buy+sell) TOP25" 풀**. 순매수/순매도 TOP10은 *이 25개 안에서* net 기준 재정렬한 것. 즉 "월별 가장 많이 거래된 25개 해외종목 중 순매수/순매도 상위 10". 거래회전이 낮은데 순매수만 큰 종목은 누락될 수 있음(단, |net| ≤ 총결제라 실무상 드묾).

---

## 2. 동봉 파일 (verify_pkg/)
| 파일 | 내용 | 검증 용도 |
|---|---|---|
| `seibro_netbuy_monthly.csv` | 월별 TOP25 tidy: month, nation, isin, name, ticker, buy_usd, sell_usd, **net_usd** (2023-01~2026-05) | **입력 유니버스**. 여기서 TOP10 재정렬 |
| `prices_monthly.csv` | **월말 adjusted_close 행렬** (index=YYYY-MM, columns=ticker, +SPY.US) | **수익률 독립 재계산** |
| `seibro_buysell_top10_all.csv` | 내가 계산한 per-pick: month, side(매수/매도), rank, ticker, net_usd, 각 horizon 수익률·SPY·alpha | 내 계산 결과 (대조 대상) |
| `seibro_debut_tracker.csv` | 종목별 debut월/데뷔가/+3M·+6M·+1Y·현재/peak순매수 | 데뷔 분석 결과 (대조 대상) |
| `recompute_canonical.py` | 동봉 CSV만으로 §4 표 + 데뷔표 전체 재생성(무 API) | **재현 검증 1순위** |
| `seibro_fetcher.py`, `seibro_netbuy_perf.py`, `seibro_debut_tracker.py` | 원천 수집/분석 스크립트(EODHD·SEIBRO 필요) | 로직 감사 |

---

## 3. 방법론
### 3-1. 매수/매도 TOP10 성과 (`seibro_netbuy_perf.py`)
- 진입 유니버스: 2024-01~2026-05 (29개월).
- 매월: net_usd **내림차순 TOP10 = "매수"**, **오름차순 TOP10 = "매도"**.
- 진입가 = 진입월 말 adjusted_close. 청산가 = (진입월+k) 말 종가, k∈{1,3,6,12}.
- 수익률 = 청산/진입 − 1. 벤치 = SPY 동일 구간. alpha = 종목수익 − SPY수익.
- 집계 = 전체 pick 단순평균/중앙/승률 (가중 없음).

### 3-2. 데뷔 추적 (`seibro_debut_tracker.py`)
- 2023-01~2026-05 매월 net 내림차순 TOP10 멤버십.
- 종목별 **debut = TOP10에 처음 든 월**. 데뷔가 = 데뷔월 말 종가. 이후 +3M/+6M/+1Y/현재 수익률.

---

## 4. 결과 (검증 대상 수치)
### 4-1. 매수 TOP10 (mode=all, 2024-01~2026-05)
| horizon | N | 평균 | 중앙 | 승률 | SPY | alpha |
|---|---|---|---|---|---|---|
| 1M | 290 | +3.7% | +1.1% | 59% | +1.7% | +2.0%p |
| 3M | 270 | +9.8% | +1.9% | 58% | +4.8% | +4.9%p |
| 6M | 240 | +15.8% | +6.1% | 61% | +9.2% | +6.7%p |
| 1Y | 180 | +33.4% | +17.5% | 73% | +18.4% | +15.1%p |

### 4-2. 매도 TOP10
| horizon | N | 평균 | 중앙 | 승률 | SPY | alpha |
|---|---|---|---|---|---|---|
| 1M | 290 | +4.0% | +0.3% | 51% | +1.7% | +2.3%p |
| 3M | 270 | +13.5% | +5.6% | 61% | +4.8% | +8.7%p |
| 6M | 240 | +25.5% | +9.2% | 64% | +9.2% | +16.4%p |
| 1Y | 180 | +53.9% | +27.8% | 76% | +18.4% | +35.6%p |

### 4-3. 매수−매도 스프레드 (alpha 차)
1M −0.3%p / 3M −3.7%p / **6M −9.7%p** / **1Y −20.5%p** (음수가 클수록 매도종목이 더 우월)

### 4-4. 데뷔 추적 하이라이트 (94종, `seibro_debut_tracker.csv`)
- 대박(2023 데뷔): SOXL(23-04 @13.9 → 현재 **+1522%**), Micron(23-04 @63.5 → **+1507%**), ARM(23-09 @53.5 → +641%), TQQQ(23-10 @15.9 → +402%), TSMC(23-01 → +381%), Intel(23-02 @24.3 → +381%), AMD(23-06 → +345%), NVDA(23-08 @49.3 → +321%).
- 폭망(고점 데뷔): First Republic(23-03 → **−100%**), 2x NatGas/BOIL(23-01 @1518 → −98%), T-Rex 2x MSTR(24-10 → −96%), Maison(23-12 → −94%), Figma(25-08 → −74%), NuScale(25-08 → −71%), Circle(25-06 @181 → −56%).
- 패턴: 데뷔 직후 +3M은 대박주조차 약세(NVDA −5%, TSMC −9%, AMD −10%, Micron +11%).

---

## 5. 알려진 한계 (검토자가 반드시 도전할 것)
1. **유니버스 편향**: 결제 TOP25 풀에서만 추출(위 §1). 시장 전체 순매수/매도 TOP가 아님.
2. **중첩 윈도우**: forward 구간이 월마다 겹침 → 관측 비독립. 특히 1Y는 진입월 ~18개뿐. 보고된 평균에 **t검정·신뢰구간 없음**. 통계적 유의성은 과대해석 금지.
3. **ETF/레버리지 포함**(mode=all): SOXL/TQQQ/단일종목 2~3x가 평균을 좌우. `mode=stocks`로 재실행 시 결과 달라질 수 있음(검증 권장).
4. **진입가 단순화**: SEIBRO 순매수는 *월중 누적*인데 진입가를 *월말 종가*로 가정. 실제 평단가 ≠ 월말종가.
5. **FX 미반영**: 수익률은 종목통화(USD) 기준. 한국 투자자 실제 원화수익률은 USDKRW 변동만큼 다름. **SPY 벤치도 USD 기준**.
6. **생존편향 가능성**: 상장폐지 종목 중 EODHD에 이력 없는 건 조용히 누락될 수 있음(단 First Republic −100%는 포함됨 → 부분적으로만 영향).
7. **ISIN→티커 해석**: EODHD search로 자동 매핑, 98/106 해결(8개 미해결 drop). 미국 외 상장(예 KIOXIA=KI5.F 프랑크푸르트) 일부 포함.
8. **결제일 기준**: SEIBRO는 결제(settlement)일 집계라 체결일과 소폭 시차.
9. **레짐 종속**: 2023~2026 테크 강세장 단일 국면. 하락장 일반화 불가.

---

## 6. 검증 체크리스트 (GPT용)
**A. 멤버십 재현** — `seibro_netbuy_monthly.csv`에서 월별 `net_usd` 내림차순 TOP10(매수)/오름차순 TOP10(매도)을 뽑아 `seibro_buysell_top10_all.csv`의 (month, side, ticker)와 일치하는지.

**B. 수익률 재계산** — `prices_monthly.csv`로 각 pick의 진입월·(진입월+k) 종가를 읽어 수익률을 재계산, 내 per-pick 값과 대조(부동소수 오차 허용).

**C. 집계 재현** — horizon별 평균/중앙/승률/alpha를 다시 집계해 §4 표와 비교.

**D. 데뷔 스폿체크** — `prices_monthly.csv`에서 NVDA(23-08), Micron(23-06), Circle(25-06), First Republic(23-03)의 데뷔가·이후 수익률이 `seibro_debut_tracker.csv`와 맞는지.

**E. 한계 도전** — (i) `seibro_netbuy_monthly.csv`의 name에서 ETF/레버리지 제외 후 매수−매도 스프레드 부호 유지되는지, (ii) 중첩 윈도우를 비중첩(분기별)으로 바꿔도 결론 유지되는지, (iii) FX(USDKRW) 반영 시 alpha 변화.

### 재현 코드 (순수 pandas, API 불필요)
```python
import pandas as pd
u = pd.read_csv("seibro_netbuy_monthly.csv", dtype={"month":str})
px = pd.read_csv("prices_monthly.csv", dtype={"month":str}).set_index("month")
H = {"1M":1,"3M":3,"6M":6,"1Y":12}
def me_ret(t, m, k):
    m2 = str(pd.Period(m,"M")+k)
    if t not in px.columns or m not in px.index or m2 not in px.index: return None
    p0, p1 = px.at[m,t], px.at[m2,t]
    return (p1/p0-1)*100 if pd.notna(p0) and pd.notna(p1) else None
rows=[]
for m, g in u.dropna(subset=["ticker","net_usd"]).groupby("month"):
    if m < "2024-01": continue                      # 매수/매도 백테스트 범위
    for side, top in [("매수",g.nlargest(10,"net_usd")),("매도",g.nsmallest(10,"net_usd"))]:
        for _,r in top.iterrows():
            rec={"month":m,"side":side,"ticker":r["ticker"]}
            for h,k in H.items():
                rec[h]=me_ret(r["ticker"],m,k)
                s=me_ret("SPY.US",m,k); rec[h+"_a"]=(rec[h]-s) if (rec[h] is not None and s is not None) else None
            rows.append(rec)
df=pd.DataFrame(rows)
for side in ["매수","매도"]:
    d=df[df.side==side]
    print(side, {h:(round(d[h].mean(),1), round(d[h+"_a"].mean(),1)) for h in H})
# 기대값: 매수 6M 평균≈+15.8, alpha≈+6.7 / 매도 6M 평균≈+25.5, alpha≈+16.4
```
이 스니펫 결과가 §4 표와 일치하면 1차 검증 통과. (동봉 `recompute_canonical.py`가 정확히 이 로직으로 §4 + 데뷔표를 재생성한다.) 불일치 시 차이 원인(반올림/결측/티커매핑)을 보고.
