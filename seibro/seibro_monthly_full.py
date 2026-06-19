"""2020-01~2026-04 월별 종합:
- 순매수 총액(당신 시리즈) + z(롤12) + 전략포지션
- 순매수 TOP10 / 순매도 TOP10 바스켓 1M forward 수익 (등가중, EODHD adj)
- 각종 승률
"""
import sys, time
from pathlib import Path
import pandas as pd, numpy as np, requests
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent / "stock-screener"))
from provider import EODHD_API_KEY
from seibro_periodic_top10 import keydisp, topn
from seibro_netbuy_nasdaq_2011 import NB


def load_all4():
    files = ["seibro_monthly_top25_2015_2020.csv", "seibro_monthly_top25_2021_2022.csv",
             "seibro_monthly_top25_2023.csv", "seibro_monthly_top25_2024-01_2026-05.csv"]
    fr = [pd.read_csv(HERE/"data"/f, dtype={"month": str, "ISIN": str}) for f in files]
    df = pd.concat(fr, ignore_index=True)
    df["net"] = pd.to_numeric(df["SUM_FRSEC_NET_BUY_AMT"], errors="coerce")
    df["buy"] = pd.to_numeric(df["SUM_FRSEC_BUY_AMT"], errors="coerce")
    df["sell"] = pd.to_numeric(df["SUM_FRSEC_SELL_AMT"], errors="coerce")
    kd = df.apply(lambda r: keydisp(r["ISIN"], r["KOR_SECN_NM"]), axis=1)
    df["key"] = [x[0] for x in kd]; df["disp"] = [x[1] for x in kd]
    return df


def me_adj(tkr):
    try:
        r = requests.get(f"https://eodhd.com/api/eod/{tkr}",
            params={"api_token": EODHD_API_KEY, "fmt": "json", "from": "2014-06-01", "to": "2026-06-18"}, timeout=30)
        a = r.json() if r.status_code == 200 else []
        if not a: return None
        d = pd.DataFrame(a); d["date"] = pd.to_datetime(d["date"])
        c = "adjusted_close" if "adjusted_close" in d else "close"
        s = d.set_index("date")[c].sort_index().resample("ME").last()
        s.index = s.index.to_period("M").astype(str); return s
    except Exception: return None


def zscore(s, w=12, mp=6):
    o = {}; v = s.values; ix = list(s.index)
    for i in range(len(ix)):
        h = v[max(0, i-w+1):i+1]
        o[ix[i]] = (v[i]-h.mean())/h.std(ddof=1) if len(h) >= mp and h.std(ddof=1) > 0 else np.nan
    return pd.Series(o)


def main():
    df = load_all4()
    months = sorted(df["month"].unique())
    mem, keys = {}, set()
    for m in months:
        b, s = topn(df[df.month == m])
        mem[m] = (list(b["key"]), list(s["key"]))
        keys |= set(b["key"]) | set(s["key"])
    px = {}
    for k in sorted(keys):
        if not k or "·" in k or "?" in k or "(" in k or k.startswith("00"):
            continue
        sp = me_adj(k if "." in k else k+".US")
        if sp is not None and len(sp) > 3: px[k] = sp
        time.sleep(0.02)

    H = {"1M": 1, "3M": 3, "6M": 6, "12M": 12}
    def fwd(keylist, m, k):
        m2 = str(pd.Period(m, "M")+k); r = []
        for key in keylist:
            sp = px.get(key)
            if sp is None or m not in sp.index or m2 not in sp.index: continue
            p0, p1 = sp[m], sp[m2]
            if pd.notna(p0) and pd.notna(p1) and p0 > 0: r.append((p1/p0-1)*100)
        return sum(r)/len(r) if r else None

    nb = pd.Series(NB); z = zscore(nb)
    rng = [f"{y}-{mo:02d}" for y in range(2015, 2027) for mo in range(1, 13)]
    rng = [m for m in rng if "2015-01" <= m <= "2026-04" and m in mem]

    # 월별 데이터 수집
    data = {}  # month -> {h:(b,s)}
    csv_rows = []
    for m in rng:
        bl, sl = mem.get(m, ([], []))
        data[m] = {h: (fwd(bl, m, k), fwd(sl, m, k)) for h, k in H.items()}
        row = {"month": m, "netbuy_M": nb.get(m, np.nan), "z": z.get(m, np.nan)}
        for h in H:
            b, s = data[m][h]
            row[f"buy_{h}"] = b; row[f"sell_{h}"] = s
            row[f"spread_{h}"] = (s-b) if (b is not None and s is not None) else None
        csv_rows.append(row)
    cdf = pd.DataFrame(csv_rows)
    cpath = HERE/"data"/"seibro_basket_fwd_2015_2026.csv"
    cdf.to_csv(cpath, index=False, encoding="utf-8-sig")
    print(f"월별 원본 저장: {cpath} ({len(cdf)}개월)\n")

    years = [str(y) for y in range(2015, 2027)]
    def cell(ms, h, kind):
        pairs = [data[m][h] for m in ms if data[m][h][0] is not None and data[m][h][1] is not None]
        n = len(pairs)
        if n == 0: return "—"
        b = [p[0] for p in pairs]; s = [p[1] for p in pairs]
        if kind == "spread": return f"{np.mean(s)-np.mean(b):+.1f}"
        if kind == "win": return f"{sum(1 for bi,si in pairs if si>bi)/n*100:.0f}%"
        if kind == "buy": return f"{np.mean(b):+.1f}"
        if kind == "sell": return f"{np.mean(s):+.1f}"
        if kind == "n": return str(n)

    for kind, title in [("spread","매도−매수 스프레드(%p)"), ("win","매도>매수 승률"),
                        ("buy","매수바스켓 평균(%)"), ("sell","매도바스켓 평균(%)"), ("n","표본월수")]:
        print(f"\n##### 연도×호라이즌 — {title} #####")
        print("| 진입연도 | 1M | 3M | 6M | 12M |")
        print("|---|--:|--:|--:|--:|")
        for y in years:
            ms = [m for m in rng if m[:4] == y]
            if not ms: continue
            print(f"| {y} | " + " | ".join(cell(ms, h, kind) for h in H) + " |")
        # 전체
        print(f"| **전체** | " + " | ".join(cell(rng, h, kind) for h in H) + " |")


if __name__ == "__main__":
    main()
