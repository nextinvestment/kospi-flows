"""사용자 제공 월별 순매수($M)와 나스닥(IXIC) 비교 차트.
- 상단: 월별 순매수 막대 + 나스닥 지수(우축)
- 하단: 누적 순매수 + 나스닥(정규화)
+ 동월/선행 상관계수.
"""
import sys
from datetime import date
from pathlib import Path
import pandas as pd, requests
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY

# 사용자 제공 월별 순매수 ($M)
DATA = {
"2021-01":4532,"2021-02":2865,"2021-03":2780,"2021-04":2100,"2021-05":263,"2021-06":247,
"2021-07":987,"2021-08":543,"2021-09":855,"2021-10":446,"2021-11":2694,"2021-12":2479,
"2022-01":2467,"2022-02":3003,"2022-03":1636,"2022-04":2510,"2022-05":1860,"2022-06":408,
"2022-07":-4,"2022-08":-572,"2022-09":291,"2022-10":198,"2022-11":478,"2022-12":-221,
"2023-01":706,"2023-02":13,"2023-03":180,"2023-04":-337,"2023-05":-1026,"2023-06":-1061,
"2023-07":-9,"2023-08":306,"2023-09":545,"2023-10":266,"2023-11":-487,"2023-12":-1922,
"2024-01":730,"2024-02":1474,"2024-03":2095,"2024-04":993,"2024-05":463,"2024-06":2113,
"2024-07":1101,"2024-08":499,"2024-09":-487,"2024-10":-761,"2024-11":1279,"2024-12":1046,
"2025-01":4078,"2025-02":2975,"2025-03":4072,"2025-04":3705,"2025-05":-1311,"2025-06":-232,
"2025-07":685,"2025-08":642,"2025-09":3184,"2025-10":6855,"2025-11":5934,"2025-12":1874,
"2026-01":5003,"2026-02":3949,"2026-03":1692,"2026-04":-469,"2026-05":-940,"2026-06":633,
}


def me(tkr):
    r = requests.get(f"https://eodhd.com/api/eod/{tkr}",
        params={"api_token": EODHD_API_KEY, "fmt": "json", "from": "2020-12-01", "to": date.today().strftime("%Y-%m-%d")}, timeout=30)
    d = pd.DataFrame(r.json()); d["date"] = pd.to_datetime(d["date"])
    c = "adjusted_close" if "adjusted_close" in d else "close"
    s = d.set_index("date")[c].sort_index().resample("ME").last()
    s.index = s.index.to_period("M").astype(str); return s


def main():
    nb = pd.Series(DATA)
    ndx = me("IXIC.INDX")
    df = pd.DataFrame({"nb": nb, "ndx": ndx}).dropna()
    df["ndx_ret"] = ndx.pct_change().reindex(df.index) * 100
    df["cum_nb"] = df["nb"].cumsum()

    # 상관
    print("##### 월별 순매수 vs 나스닥 상관 #####")
    c0 = df["nb"].corr(df["ndx_ret"])
    c_lead1 = df["nb"].corr(df["ndx_ret"].shift(-1))   # 순매수가 다음달 수익 선행?
    c_lag1 = df["nb"].corr(df["ndx_ret"].shift(1))     # 순매수가 전달 수익 추종?
    print(f"  동월         corr(순매수, 나스닥수익) = {c0:+.2f}")
    print(f"  순매수→다음달  corr = {c_lead1:+.2f}  (양수면 순매수 많을때 다음달 상승)")
    print(f"  전달수익→순매수 corr = {c_lag1:+.2f}  (양수면 오른 다음달 더 매수=추격)")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["font.family"] = "Malgun Gothic"
    matplotlib.rcParams["axes.unicode_minus"] = False

    x = list(range(len(df))); labels = list(df.index)
    fig, ax = plt.subplots(2, 1, figsize=(15, 10))

    # 상단: 순매수 막대 + 나스닥 라인
    colors = ["#d62728" if v >= 0 else "#1f77b4" for v in df["nb"]]
    ax[0].bar(x, df["nb"], color=colors, width=0.8)
    ax[0].axhline(0, color="k", lw=.6)
    ax[0].set_ylabel("월별 순매수 ($M)")
    ax2 = ax[0].twinx()
    ax2.plot(x, df["ndx"], color="black", lw=1.6, label="나스닥(IXIC)")
    ax2.set_ylabel("나스닥 지수")
    ax[0].set_title(f"월별 순매수(막대) vs 나스닥 지수(선)  ·  동월상관 {c0:+.2f} / 추격성향 {c_lag1:+.2f}")
    step = max(1, len(x)//22)
    ax[0].set_xticks(x[::step]); ax[0].set_xticklabels(labels[::step], rotation=45, fontsize=7)
    ax2.legend(loc="upper left")

    # 하단: 누적 순매수 vs 나스닥(정규화)
    ax[1].plot(x, df["cum_nb"], color="#2ca02c", lw=2, label="누적 순매수($M)")
    ax[1].set_ylabel("누적 순매수 ($M)", color="#2ca02c")
    ax3 = ax[1].twinx()
    ax3.plot(x, df["ndx"], color="black", lw=1.4, label="나스닥(IXIC)")
    ax3.set_ylabel("나스닥 지수")
    ax[1].set_title("누적 순매수 vs 나스닥")
    ax[1].set_xticks(x[::step]); ax[1].set_xticklabels(labels[::step], rotation=45, fontsize=7)
    ax[1].axhline(0, color="k", lw=.5)

    fig.suptitle("서학개미 월별 순매수 vs 나스닥 (2021~2026)", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = HERE / "data" / "seibro_netbuy_vs_nasdaq.png"
    fig.savefig(out, dpi=130)
    print(f"\n저장: {out}")

    # 극단 달
    print("\n순매수 최대 5개월:")
    for k, v in df["nb"].nlargest(5).items(): print(f"  {k}: +{v:,}M  (나스닥 그달 {df.loc[k,'ndx_ret']:+.1f}%)")
    print("순매도(최소) 5개월:")
    for k, v in df["nb"].nsmallest(5).items(): print(f"  {k}: {v:,}M  (나스닥 그달 {df.loc[k,'ndx_ret']:+.1f}%)")


if __name__ == "__main__":
    main()
