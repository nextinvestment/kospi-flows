"""After daily ingest: commit parquet to GitHub, post Telegram summary with Streamlit URL.

Streamlit Community Cloud auto-redeploys on push, so the link in the Telegram
message will show the freshest data once Cloud's build finishes (~30-60s).
"""
from __future__ import annotations

import os
import subprocess
import sys
import datetime as dt
from pathlib import Path

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
TG_API = "https://api.telegram.org/bot{token}/sendMessage"


def load_env():
    env = HERE / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> tuple[int, str]:
    print(f"    $ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=False)
    out = (r.stdout or "") + (r.stderr or "")
    if out.strip():
        for line in out.rstrip().splitlines():
            print(f"      {line}")
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed (rc={r.returncode}): {cmd}")
    return r.returncode, out


def git_commit_and_push(token: str | None, user: str, repo: str) -> bool:
    """Stage data/ + code, commit, push. Returns True if a commit was made."""
    if not (HERE / ".git").exists():
        print("    .git missing — skipping push")
        return False
    # stage parquet + code (any tracked changes)
    run(["git", "add", "-A"], cwd=HERE)
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    rc, _ = run(["git", "commit", "-m", f"Daily flow update {ts}"], cwd=HERE, check=False)
    if rc != 0:
        print("      (no changes to commit)")
        return False
    if token:
        remote = f"https://{token}@github.com/{user}/{repo}.git"
    else:
        remote = "origin"
    run(["git", "push", remote, "HEAD:main"], cwd=HERE)
    return True


def _name_map() -> dict[str, str]:
    uni_path = HERE / "data" / "kospi_universe.csv"
    if uni_path.exists():
        uni = pd.read_csv(uni_path, dtype={"code": str})
        return dict(zip(uni["code"], uni["name"]))
    from config import WATCHLIST
    return WATCHLIST


def _fmt_row(i: int, name: str, val: float, ret: float) -> str:
    return f"  {i:>2}. {name} {val:+,.0f}  ({ret:+.1f}%)"


def _fmt_cum(i: int, name: str, cum: float, inst: float, days: int) -> str:
    return f"  {i:>2}. {name} {cum:+,.0f}억  (기관 {inst:+,.0f}, {days}d)"


def build_summary() -> list[str]:
    """Return one-or-more Telegram messages (each ≤ 4096 chars).

    Message 1: market summary + daily TOP15 buy/sell
    Message 2: N-day cumulative + co-trades + streaks + dashboard link
    """
    import analytics
    mp = HERE / "data" / "market_flows.parquet"
    sp = HERE / "data" / "stock_flows.parquet"
    ip = HERE / "data" / "kospi_index.parquet"
    if not mp.exists():
        return ["<b>KOSPI Flows</b>\n(no market data yet)"]

    m = pd.read_parquet(mp)
    m = m[m["market"] == "KOSPI"].sort_values("date")
    latest = m.iloc[-1]
    d = pd.Timestamp(latest["date"]).strftime("%Y-%m-%d")

    cum5 = m.tail(5)[["외국인", "기관계", "개인"]].sum()
    cum20 = m.tail(20)[["외국인", "기관계", "개인"]].sum()

    # ----- MESSAGE 1: market summary + daily TOP15 -----
    lines = [
        f"<b>📊 KOSPI 수급 — {d}</b>",
    ]

    # KOSPI index price + divergence
    if ip.exists():
        idx = pd.read_parquet(ip)
        kospi_idx = idx[idx["index_code"] == "KOSPI"].sort_values("date")
        if not kospi_idx.empty:
            iv = kospi_idx.iloc[-1]
            lines += [f"KOSPI {iv['close']:,.2f} ({iv['ret_pct']:+.2f}%)"]
            div = analytics.divergence_check(m, kospi_idx, window=20)
            if div.get("available"):
                lines += ["", div["msg"]]

    lines += [
        "",
        f"<b>당일 (억원)</b>",
        f"  외국인: {latest['외국인']:+,.0f}",
        f"  기관계: {latest['기관계']:+,.0f}",
        f"  개인:   {latest['개인']:+,.0f}",
        "",
        f"<b>5일 누적</b>  외국인 {cum5['외국인']:+,.0f}  /  기관 {cum5['기관계']:+,.0f}  /  개인 {cum5['개인']:+,.0f}",
        f"<b>20일 누적</b> 외국인 {cum20['외국인']:+,.0f}  /  기관 {cum20['기관계']:+,.0f}  /  개인 {cum20['개인']:+,.0f}",
    ]

    msg1_extra: list[str] = []
    msg2_lines: list[str] = []

    if sp.exists():
        s = pd.read_parquet(sp)
        s["date"] = pd.to_datetime(s["date"])
        nm = _name_map()
        d_latest = s["date"].max()
        day = s[s["date"] == d_latest].copy()
        if not day.empty:
            day["foreign_value"] = day["foreign_net"] * day["close"] / 1e8
            day["name"] = day["code"].map(nm).fillna(day["code"])

            top = day.nlargest(15, "foreign_value")[["name", "foreign_value", "ret_pct"]]
            bot = day.nsmallest(15, "foreign_value")[["name", "foreign_value", "ret_pct"]]
            msg1_extra += [
                "",
                f"<b>당일 외국인 순매수 TOP 15 (억원)</b>",
                "<blockquote expandable>",
                *[_fmt_row(i, n, v, r)
                  for i, (n, v, r) in enumerate(zip(top["name"], top["foreign_value"], top["ret_pct"]), 1)],
                "</blockquote>",
                "",
                f"<b>당일 외국인 순매도 TOP 15 (억원)</b>",
                "<blockquote expandable>",
                *[_fmt_row(i, n, v, r)
                  for i, (n, v, r) in enumerate(zip(bot["name"], bot["foreign_value"], bot["ret_pct"]), 1)],
                "</blockquote>",
            ]

        # ----- MESSAGE 2: cumulative + co-trades + streaks -----
        msg2_lines.append(f"<b>📊 KOSPI 수급 — {d} (계속)</b>")

        for n_days, label in [(5, "5일"), (20, "20일")]:
            cb, cs = analytics.n_day_cumulative_top(s, n_days=n_days, top_k=10, name_map=nm)
            if not cb.empty:
                msg2_lines += [
                    "",
                    f"<b>{label} 누적 외국인 매수 TOP 10</b>",
                    "<blockquote expandable>",
                    *[_fmt_cum(i, r.name, r.cum_foreign, r.cum_inst, r.days_traded)
                      for i, r in enumerate(cb.itertuples(index=False), 1)],
                    "</blockquote>",
                ]
            if not cs.empty:
                msg2_lines += [
                    "",
                    f"<b>{label} 누적 외국인 매도 TOP 10</b>",
                    "<blockquote expandable>",
                    *[_fmt_cum(i, r.name, r.cum_foreign, r.cum_inst, r.days_traded)
                      for i, r in enumerate(cs.itertuples(index=False), 1)],
                    "</blockquote>",
                ]

        co_buy, co_sell = analytics.co_buying_selling(s, top_k=10, name_map=nm)
        if not co_buy.empty:
            msg2_lines += [
                "",
                f"<b>🟢 외국인+기관 동반 매수 TOP 10 (억원)</b>",
                "<blockquote expandable>",
                *[f"  {i:>2}. {r.name} 외국인 {r.foreign_value:+,.0f}  기관 {r.inst_value:+,.0f}"
                  for i, r in enumerate(co_buy.itertuples(index=False), 1)],
                "</blockquote>",
            ]
        if not co_sell.empty:
            msg2_lines += [
                "",
                f"<b>🔴 외국인+기관 동반 매도 TOP 10 (억원)</b>",
                "<blockquote expandable>",
                *[f"  {i:>2}. {r.name} 외국인 {r.foreign_value:+,.0f}  기관 {r.inst_value:+,.0f}"
                  for i, r in enumerate(co_sell.itertuples(index=False), 1)],
                "</blockquote>",
            ]

        sb = analytics.consecutive_streak(s, min_days=5, direction="buy", name_map=nm).head(10)
        ss = analytics.consecutive_streak(s, min_days=5, direction="sell", name_map=nm).head(10)
        if not sb.empty:
            msg2_lines += [
                "",
                f"<b>📈 5일+ 연속 외국인 매수 (TOP 10)</b>",
                "<blockquote expandable>",
                *[f"  {i:>2}. {r.name} {int(r.streak_days)}일 연속 (누적 {r.cum_foreign_value:+,.0f}억)"
                  for i, r in enumerate(sb.itertuples(index=False), 1)],
                "</blockquote>",
            ]
        if not ss.empty:
            msg2_lines += [
                "",
                f"<b>📉 5일+ 연속 외국인 매도 (TOP 10)</b>",
                "<blockquote expandable>",
                *[f"  {i:>2}. {r.name} {int(r.streak_days)}일 연속 (누적 {r.cum_foreign_value:+,.0f}억)"
                  for i, r in enumerate(ss.itertuples(index=False), 1)],
                "</blockquote>",
            ]

    url = os.environ.get("STREAMLIT_URL", "").strip()
    tail = ["", f'<a href="{url}">→ 대시보드 열기</a>'] if url else []

    msg1 = "\n".join(lines + msg1_extra)
    msg2 = "\n".join(msg2_lines + tail) if msg2_lines else None
    out = [msg1]
    if msg2:
        out.append(msg2)
    return out


def send_telegram(token: str, chat_id: str, text: str) -> dict:
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _d = _Path(__file__).resolve().parent.parent / "stock-screener"
        if _d.exists() and str(_d) not in _sys.path:
            _sys.path.insert(0, str(_d))
        from tg_subscribers import broadcast_targets
        targets = broadcast_targets(chat_id)
    except Exception:
        targets = [c.strip() for c in str(chat_id).split(",") if c.strip()]
    res = {}
    for cid in targets:
        try:
            r = requests.post(
                TG_API.format(token=token),
                json={"chat_id": cid, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": False},
                timeout=30,
            )
            r.raise_for_status()
            res = r.json()
        except Exception as e:
            print(f"  ! telegram send to {cid} failed: {e}")
    return res


def main():
    load_env()
    tg_token = os.environ.get("TG_BOT_TOKEN")
    chat_id = os.environ.get("TG_CHAT_ID")
    gh_token = os.environ.get("GH_TOKEN")
    gh_user = os.environ.get("GH_USER", "nextinvestment")
    gh_repo = os.environ.get("GH_REPO", "kospi-flows")

    if not tg_token or not chat_id:
        print("ERROR: TG_BOT_TOKEN / TG_CHAT_ID missing in .env")
        sys.exit(1)

    print(f"[push_and_notify] {dt.date.today()}")

    pushed = False
    try:
        pushed = git_commit_and_push(gh_token, gh_user, gh_repo)
    except Exception as e:
        print(f"  ! git push failed: {e}")
        # continue to telegram anyway

    messages = build_summary()
    if not pushed:
        messages[-1] += "\n\n<i>(데이터 변경 없음 — 사이트 갱신 없음)</i>"

    for i, text in enumerate(messages, 1):
        print(f"  posting to Telegram ({i}/{len(messages)}, {len(text)} chars) ...")
        resp = send_telegram(tg_token, chat_id, text)
        ok = resp.get("ok", False)
        print(f"    ok={ok}  message_id={resp.get('result', {}).get('message_id')}")
        if not ok:
            print(f"    response: {resp}")
            sys.exit(2)


if __name__ == "__main__":
    main()
