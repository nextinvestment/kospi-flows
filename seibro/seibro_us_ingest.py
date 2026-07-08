"""서학개미 미국주식 순매수 — 공식 결제금액 일일 인제스트 + 차트 재생성.

사용자가 예탁결제원 국가별 결제금액 표의 '주식' 행을 붙여주면, 미국 매도/매수만
뽑아 data/seibro_us_daily.csv 에 upsert(날짜 키 중복제거)하고 차트를 다시 그린다.

파싱 규칙: 한 줄에서 첫 토큰=날짜(YYYYMMDD), '주식' 포함 행만 사용.
숫자 토큰 순서 = [유로매도,유로매수, 미국매도,미국매수, 일본…]. 미국 = 3·4번째 숫자.
'날짜 미국매도 미국매수' 3열만 붙여도 인식.

    python seibro_us_ingest.py <붙인내용파일.txt>     # 인제스트 + 차트
    python seibro_us_ingest.py --draw                 # 저장분으로 차트만
"""
import re
import sys
from datetime import date
from pathlib import Path
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
STORE = HERE / "data" / "seibro_us_daily.csv"
sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
import requests

NUM = re.compile(r"-?\d*\.?\d+")


def parse(text: str) -> pd.DataFrame:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"(\d{8})", line)
        if not m:
            continue
        d = m.group(1)
        is_stock = "주식" in line
        is_bond = "채권" in line
        if is_bond and not is_stock:
            continue  # 채권 행 스킵
        nums = [float(x) for x in NUM.findall(line[8:])]
        if is_stock:                       # 전체 표 행: 유로(0,1) 미국(2,3)…
            if len(nums) < 4:
                continue
            sell, buy = nums[2], nums[3]
        else:                              # '날짜 미국매도 미국매수' 3열 축약
            if len(nums) < 2:
                continue
            sell, buy = nums[0], nums[1]
        per = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        rows.append({"date": per, "us_sell": sell, "us_buy": buy, "us_net": round(buy - sell, 2)})
    return pd.DataFrame(rows)


def upsert(new: pd.DataFrame) -> pd.DataFrame:
    if STORE.exists():
        old = pd.read_csv(STORE)
        both = pd.concat([old, new], ignore_index=True)
    else:
        both = new
    both = both.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    both.to_csv(STORE, index=False, encoding="utf-8-sig")
    return both


def draw(df: pd.DataFrame):
    df = df.copy()
    df["dt"] = pd.to_datetime(df["date"])
    df["month"] = df["dt"].dt.to_period("M").astype(str)
    mon = df.groupby("month")["us_net"].sum()
    r = requests.get("https://eodhd.com/api/eod/IXIC.INDX",
        params={"api_token": EODHD_API_KEY, "fmt": "json", "from": "2023-12-01",
                "to": date.today().strftime("%Y-%m-%d")}, timeout=30)
    nd = pd.DataFrame(r.json()); nd["date"] = pd.to_datetime(nd["date"])
    c = "adjusted_close" if "adjusted_close" in nd else "close"
    ndx_m = nd.set_index("date")[c].resample("ME").last(); ndx_m.index = ndx_m.index.to_period("M").astype(str)
    ndx_d = nd.set_index("date")[c].reindex(df.set_index("dt").index, method="ffill")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["font.family"] = "Malgun Gothic"; matplotlib.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(2, 1, figsize=(16, 10))
    x = list(range(len(mon))); lab = list(mon.index)
    col = ["#d62728" if v >= 0 else "#1f77b4" for v in mon.values]
    ax[0].bar(x, mon.values, color=col, width=.75); ax[0].axhline(0, color="k", lw=.6)
    ax[0].set_ylabel("월 순매수 ($M)")
    a2 = ax[0].twinx(); a2.plot(x, ndx_m.reindex(mon.index).values, color="k", lw=1.8, label="나스닥")
    a2.legend(loc="upper left"); a2.set_ylabel("나스닥")
    ax[0].set_title("공식 미국주식 월 순매수 vs 나스닥 (일일 결제금액 집계)")
    step = max(1, len(x)//24); ax[0].set_xticks(x[::step]); ax[0].set_xticklabels(lab[::step], rotation=45, fontsize=7)
    dd = df.sort_values("dt"); dd["cum"] = dd["us_net"].cumsum()
    ax[1].plot(range(len(dd)), dd["cum"].values, color="#2ca02c", lw=1.8, label="누적 순매수")
    ax[1].set_ylabel("누적 순매수 ($M)", color="#2ca02c")
    a3 = ax[1].twinx(); a3.plot(range(len(dd)), ndx_d.values, color="k", lw=1.2); a3.set_ylabel("나스닥")
    ax[1].set_title("일별 누적 미국주식 순매수 vs 나스닥"); ax[1].legend(loc="upper left")
    li = list(dd["date"]); s2 = max(1, len(li)//24)
    ax[1].set_xticks(range(0, len(li), s2)); ax[1].set_xticklabels(li[::s2], rotation=45, fontsize=7)
    fig.suptitle(f"서학개미 미국주식 순매수 (공식 결제금액)  ·  {df['date'].min()} ~ {df['date'].max()}", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = HERE / "data" / "seibro_us_daily.png"; fig.savefig(out, dpi=130)
    print(f"차트: {out}")


if __name__ == "__main__":
    if "--draw" in sys.argv:
        df = pd.read_csv(STORE)
    else:
        if len(sys.argv) < 2:
            print("사용법: python seibro_us_ingest.py <붙인내용.txt>  |  --draw"); sys.exit(1)
        text = Path(sys.argv[1]).read_text(encoding="utf-8")
        new = parse(text)
        if new.empty:
            print("파싱된 행 없음 — '주식' 행 또는 '날짜 매도 매수' 형식인지 확인"); sys.exit(1)
        df = upsert(new)
        print(f"인제스트 {len(new)}행 → 저장 총 {len(df)}행 ({df['date'].min()}~{df['date'].max()})")
        print("최근 5행:"); print(df.tail(5).to_string(index=False))
    draw(df)
