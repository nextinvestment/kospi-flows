"""공식 미국 주식 순매수(결제금액, 검증본) vs 나스닥 + 트래커(top-50) 대조.

- 상단: 공식 월 순매수(매수-매도, 막대) + 나스닥(선)
- 하단: 공식(전체 US) vs 트래커(SEIBRO top-50) 겹쳐 → 최근 divergence 가시화
데이터: 사용자 제공 예탁결제원 결제금액 표(미국 주식 매수-매도, $M). 2026-06 정정(+633).
"""
import sys
from datetime import date
from pathlib import Path
import pandas as pd, numpy as np, requests
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY

OFF = {"2024-01":730,"2024-02":1474,"2024-03":2095,"2024-04":993,"2024-05":463,"2024-06":2113,
"2024-07":1101,"2024-08":499,"2024-09":-487,"2024-10":-761,"2024-11":1279,"2024-12":1046,
"2025-01":4078,"2025-02":2975,"2025-03":4072,"2025-04":3705,"2025-05":-1311,"2025-06":-232,
"2025-07":685,"2025-08":642,"2025-09":3184,"2025-10":6855,"2025-11":5934,"2025-12":1874,
"2026-01":5003,"2026-02":3949,"2026-03":1692,"2026-04":-469,"2026-05":-940,"2026-06":633}
TOP50 = {"2024-01":786,"2024-02":1513,"2024-03":1935,"2024-04":1020,"2024-05":47,"2024-06":1901,
"2024-07":980,"2024-08":733,"2024-09":-895,"2024-10":-1106,"2024-11":873,"2024-12":1085,
"2025-01":2787,"2025-02":2327,"2025-03":4248,"2025-04":3520,"2025-05":-1517,"2025-06":-619,
"2025-07":-68,"2025-08":22,"2025-09":1409,"2025-10":4012,"2025-11":6350,"2025-12":1964,
"2026-01":2777,"2026-02":3636,"2026-03":1933,"2026-04":-615,"2026-05":431,"2026-06":2220}


def nasdaq():
    r = requests.get("https://eodhd.com/api/eod/IXIC.INDX",
        params={"api_token": EODHD_API_KEY, "fmt": "json", "from": "2023-12-01",
                "to": date.today().strftime("%Y-%m-%d")}, timeout=30)
    d = pd.DataFrame(r.json()); d["date"] = pd.to_datetime(d["date"])
    c = "adjusted_close" if "adjusted_close" in d else "close"
    s = d.set_index("date")[c].sort_index().resample("ME").last()
    s.index = s.index.to_period("M").astype(str); return s


def main():
    off = pd.Series(OFF); t50 = pd.Series(TOP50)
    ndx = nasdaq().reindex(off.index)
    ndx_ret = pd.Series(OFF).index.map(lambda m: None)  # placeholder
    c0 = off.corr(nasdaq().pct_change().reindex(off.index) * 100)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams["font.family"] = "Malgun Gothic"
    matplotlib.rcParams["axes.unicode_minus"] = False
    x = list(range(len(off))); labels = list(off.index)
    fig, ax = plt.subplots(2, 1, figsize=(16, 10))

    # 상단: 공식 순매수 막대 + 나스닥
    colors = ["#d62728" if v >= 0 else "#1f77b4" for v in off.values]
    ax[0].bar(x, off.values, color=colors, width=0.75)
    ax[0].axhline(0, color="k", lw=.6); ax[0].set_ylabel("공식 미국 월 순매수 ($M)")
    a2 = ax[0].twinx(); a2.plot(x, ndx.values, color="black", lw=1.8, label="나스닥")
    a2.set_ylabel("나스닥"); a2.legend(loc="upper left")
    # 최근 순매도 국면 음영 (2025-05, 2026-04~05)
    for m in ["2025-05","2026-04","2026-05"]:
        i = labels.index(m); ax[0].axvspan(i-.5, i+.5, color="#1f77b4", alpha=.08)
    ax[0].set_title(f"공식 미국주식 순매수(매수-매도) vs 나스닥  ·  동월상관 {c0:+.2f}  ·  파란음영=순매도 전환달")
    ax[0].set_xticks(x); ax[0].set_xticklabels(labels, rotation=45, fontsize=7)

    # 하단: 공식 vs 트래커
    ax[1].plot(x, off.values, color="#2ca02c", lw=2.2, marker="o", ms=3, label="공식(전체 US)")
    ax[1].plot(x, t50.values, color="#ff7f0e", lw=1.8, marker="s", ms=3, label="트래커(SEIBRO top-50)")
    ax[1].axhline(0, color="k", lw=.6); ax[1].set_ylabel("월 순매수 ($M)")
    ax[1].fill_between(x, off.values, t50.values, color="gray", alpha=.12)
    # 부호 갈린 달 강조
    for i, m in enumerate(labels):
        if (off[m] > 0) != (t50[m] > 0):
            ax[1].axvspan(i-.5, i+.5, color="red", alpha=.12)
            ax[1].annotate("부호반대", (i, min(off[m], t50[m])), fontsize=7, color="red",
                           ha="center", va="top")
    ax[1].legend(loc="upper left")
    ax[1].set_title("공식(전체 US) vs 트래커(top-50)  ·  상관 0.91 / 부호일치 93%  ·  빨강=부호 반대(트래커 오판)")
    ax[1].set_xticks(x); ax[1].set_xticklabels(labels, rotation=45, fontsize=7)

    fig.suptitle("서학개미 미국주식 순매수: 공식 결제금액 vs 트래커 vs 나스닥 (2024~2026)", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = HERE / "data" / "seibro_official_vs_tracker.png"
    fig.savefig(out, dpi=130); print(f"저장: {out}")

    # 요약
    print(f"\n동월 상관(공식 vs 나스닥): {c0:+.2f}")
    print("최근 6개월 공식 순매수($M):", {m: OFF[m] for m in labels[-6:]})
    print("→ 2026-04·05 순매도 전환(-469/-940), 트래커는 05월 +431로 매수 오판")


if __name__ == "__main__":
    main()
