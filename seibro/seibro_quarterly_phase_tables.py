"""서학개미 순매수/순매도 TOP10 — 분기별 + 국면별, 결제액(매수+매도) 포함.
캐시 월별 CSV(2021~2026)만 사용. 단위 $M. 출력은 markdown 표.
"""
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from seibro_periodic_top10 import load_all, lab

# 분기 → 국면(레짐) 매핑
def phase_of(q):
    y, qn = int(q[:4]), int(q[-1])
    if y == 2021:
        return "① 2021 버블·밈 (강세 후기)"
    if y == 2022:
        return "② 2022 약세장 (연준 긴축)"
    if y == 2023:
        return "③ 2023 AI 1막 (바닥반등)"
    if y == 2024:
        return "④ 2024 AI 강세장"
    return "⑤ 2025~26 (테마 확산)"


def topn(sub, n=10):
    g = sub.groupby("key", as_index=False).agg(
        net=("net", "sum"), buy=("buy", "sum"), sell=("sell", "sum"),
        disp=("disp", "first"))
    g["settle"] = g["buy"] + g["sell"]  # 결제액 = 매수 + 매도
    return g.nlargest(n, "net"), g.nsmallest(n, "net").sort_values("net")


def m(x):
    return round(x / 1e6)


def md_table(buy_g, sell_g, desc=True):
    out = []
    out.append("| # | 순매수 종목 | 순매수$M | 결제액$M | 순매도 종목 | 순매도$M | 결제액$M |")
    out.append("|--:|---|--:|--:|---|--:|--:|")
    bl = list(buy_g.iterrows())
    sl = list(sell_g.iterrows())
    for i in range(max(len(bl), len(sl))):
        if i < len(bl):
            r = bl[i][1]
            bcell = f"{lab(r['disp'], desc)} | {m(r['net']):+,} | {m(r['settle']):,}"
        else:
            bcell = " |  | "
        if i < len(sl):
            r = sl[i][1]
            scell = f"{lab(r['disp'], desc)} | {m(r['net']):+,} | {m(r['settle']):,}"
        else:
            scell = " |  | "
        out.append(f"| {i+1} | {bcell} | {scell} |")
    return "\n".join(out)


def main():
    df = load_all()
    df["q"] = df["month"].map(lambda x: f"{x[:4]}Q{(int(x[5:7])-1)//3+1}")
    months = sorted(df["month"].unique())
    print(f"데이터: {months[0]} ~ {months[-1]} ({len(months)}개월) · 단위 $M · 결제액=매수+매도\n")

    # ===== 분기별 =====
    print("# 분기별 서학개미 순매수/순매도 TOP10\n")
    for q in sorted(df["q"].unique()):
        sub = df[df.q == q]
        b, s = topn(sub)
        tot_settle = m(sub["buy"].sum() + sub["sell"].sum())
        tot_net = m(sub["net"].sum())
        print(f"## {q}  · top50종 결제액 합 ${tot_settle:,}M · 순매수합 {tot_net:+,}M\n")
        print(md_table(b, s, desc=True))
        print()

    # ===== 국면별 =====
    df["phase"] = df["q"].map(phase_of)
    print("\n# 국면(레짐)별 서학개미 순매수/순매도 TOP10\n")
    for ph in sorted(df["phase"].unique()):
        sub = df[df.phase == ph]
        qs = sorted(sub["q"].unique())
        b, s = topn(sub)
        tot_settle = m(sub["buy"].sum() + sub["sell"].sum())
        tot_net = m(sub["net"].sum())
        print(f"## {ph}  ({qs[0]}~{qs[-1]})  · 결제액 합 ${tot_settle:,}M · 순매수합 {tot_net:+,}M\n")
        print(md_table(b, s, desc=True))
        print()


if __name__ == "__main__":
    main()
