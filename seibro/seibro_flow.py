"""seibro_flow — 종목·기간을 주면 서학개미 순매수/매수/매도 총액을 반환.

설계 (SEIBRO 제약 반영):
  * getImptFrcurStkSetlAmtList 는 기간 무관 '결제금액(buy+sell) 상위 50종'만 반환.
    페이지네이션(PG_*) 무효. → top-50 밖 종목은 그 기간 조회 불가.
  * 단, top-50에 들면 그 종목의 buy/sell/net 은 해당 기간에 대해 정확·완전.
  * 전 기간 단건은 무겁고 타임아웃 → **월별 청크로 쪼개 합산**(부분월은 실제 일자 경계).
    월 단위로는 순위가 올라가 잡힐 확률이 높아 커버리지도 개선.

반환: dict(buy_usd, sell_usd, net_usd, months_total, months_found, missing_months, monthly[])
단위: USD. net = buy - sell (SEIBRO 제공값 그대로).
"""
from __future__ import annotations
import json, re, sys, time
from pathlib import Path
import pandas as pd
import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from seibro_fetcher import URL, HEADERS, _parse

_CACHE = json.loads((HERE / "data" / "isin_ticker_cache.json").read_text(encoding="utf-8"))
_TKR2ISIN = {v: k for k, v in _CACHE.items() if v}     # ticker -> isin
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def _fetch(sd: str, ed: str, retries: int = 3, timeout: int = 60) -> pd.DataFrame:
    """결제금액 top-50 (기간=sd..ed, YYYYMMDD). 재시도 포함."""
    xml = (
        '<reqParam action="getImptFrcurStkSetlAmtList" '
        'task="ksd.safe.bip.cnts.OvsSec.process.OvsSecIsinPTask">'
        '<MENU_NO value="921"/><CMM_BTN_ABBR_NM value=""/>'
        '<W2XPATH value="/IPORTAL/user/ovsSec/BIP_CNTS10013V.xml"/>'
        '<PG_START value="1"/><PG_END value="50"/>'
        f'<START_DT value="{sd}"/><END_DT value="{ed}"/>'
        '<S_TYPE value="2"/><S_COUNTRY value="ALL"/><D_TYPE value="1"/></reqParam>'
    )
    last = None
    for i in range(retries):
        try:
            r = requests.post(URL, data=xml.encode("utf-8"), headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            df = _parse(r.text)
            for c in ("SUM_FRSEC_BUY_AMT", "SUM_FRSEC_SELL_AMT", "SUM_FRSEC_NET_BUY_AMT"):
                if c in df:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df
        except Exception as e:
            last = e; time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"SEIBRO fetch failed {sd}-{ed}: {last}")


def _resolve(query: str):
    """입력을 (isin or None, name_substr or None) 매처로."""
    q = query.strip()
    if _ISIN_RE.match(q):
        return q, None
    if q in _TKR2ISIN:                       # ticker (e.g. NVDA.US or NVDA)
        return _TKR2ISIN[q], None
    if q + ".US" in _TKR2ISIN:
        return _TKR2ISIN[q + ".US"], None
    return None, q.upper()                    # name substring fallback


def _month_chunks(start: str, end: str):
    """[start,end] (YYYY-MM-DD) → [(yyyymmdd, yyyymmdd)] per overlapping month."""
    s = pd.Timestamp(start); e = pd.Timestamp(end)
    out = []
    cur = pd.Period(s, freq="M")
    while cur.start_time <= e:
        a = max(s, cur.start_time); b = min(e, cur.end_time)
        out.append((str(cur), a.strftime("%Y%m%d"), b.strftime("%Y%m%d")))
        cur += 1
    return out


def get_flow(query: str, start: str, end: str, pause: float = 0.3, verbose: bool = False) -> dict:
    isin, name_sub = _resolve(query)
    chunks = _month_chunks(start, end)
    buy = sell = net = 0.0
    found, missing, monthly = [], [], []
    matched_name = matched_isin = None
    for ym, sd, ed in chunks:
        df = _fetch(sd, ed)
        if isin is not None:
            row = df[df["ISIN"] == isin]
        else:
            row = df[df["KOR_SECN_NM"].str.upper().str.contains(name_sub, na=False)]
        if len(row):
            r = row.iloc[0]
            matched_name = r["KOR_SECN_NM"]; matched_isin = r["ISIN"]
            b = float(r["SUM_FRSEC_BUY_AMT"]); s = float(r["SUM_FRSEC_SELL_AMT"]); n = float(r["SUM_FRSEC_NET_BUY_AMT"])
            buy += b; sell += s; net += n
            found.append(ym)
            monthly.append({"month": ym, "buy": b, "sell": s, "net": n, "rank": int(r["RNUM"]) if pd.notna(r.get("RNUM")) else None})
        else:
            missing.append(ym)
            monthly.append({"month": ym, "buy": None, "sell": None, "net": None, "rank": None})
        if verbose:
            print(f"  {ym}: " + ("net %+.0fM (rank %s)" % (monthly[-1]['net']/1e6, monthly[-1]['rank']) if monthly[-1]['net'] is not None else "top-50 미달"))
        time.sleep(pause)
    return {
        "query": query, "isin": matched_isin or isin, "name": matched_name,
        "start": start, "end": end,
        "buy_usd": buy, "sell_usd": sell, "net_usd": net,
        "months_total": len(chunks), "months_found": len(found),
        "missing_months": missing, "monthly": monthly,
        "coverage_note": ("완전" if not missing else
                          f"부분: {len(missing)}개월 top-50 미달(해당월 수급 누락, 합계는 하한값)"),
    }


def _print(res: dict):
    print(f"\n=== 서학개미 수급: {res['name'] or res['query']} ({res['isin']}) | {res['start']} ~ {res['end']} ===")
    print(f"  순매수 총합 : ${res['net_usd']/1e6:,.1f}M")
    print(f"  매수 총액   : ${res['buy_usd']/1e6:,.1f}M")
    print(f"  매도 총액   : ${res['sell_usd']/1e6:,.1f}M")
    print(f"  커버리지    : {res['months_found']}/{res['months_total']}개월 — {res['coverage_note']}")
    if res["missing_months"]:
        print(f"  누락(top50미달): {', '.join(res['missing_months'])}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 3:
        print("usage: python seibro_flow.py <ticker|ISIN|name> <YYYY-MM-DD start> <YYYY-MM-DD end>")
        sys.exit(1)
    res = get_flow(a[0], a[1], a[2], verbose=True)
    _print(res)
