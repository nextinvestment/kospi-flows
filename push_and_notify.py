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


def build_summary() -> str:
    """Read latest parquet, produce a Telegram-formatted summary."""
    mp = HERE / "data" / "market_flows.parquet"
    sp = HERE / "data" / "stock_flows.parquet"
    if not mp.exists():
        return "<b>KOSPI Flows</b>\n(no market data yet)"

    m = pd.read_parquet(mp)
    m = m[m["market"] == "KOSPI"].sort_values("date")
    latest = m.iloc[-1]
    d = pd.Timestamp(latest["date"]).strftime("%Y-%m-%d")

    # 5d / 20d cumulative
    cum5 = m.tail(5)[["외국인", "기관계", "개인"]].sum()
    cum20 = m.tail(20)[["외국인", "기관계", "개인"]].sum()

    lines = [
        f"<b>📊 KOSPI 수급 — {d}</b>",
        "",
        f"<b>당일 (억원)</b>",
        f"  외국인: {latest['외국인']:+,.0f}",
        f"  기관계: {latest['기관계']:+,.0f}",
        f"  개인:   {latest['개인']:+,.0f}",
        "",
        f"<b>5일 누적</b>  외국인 {cum5['외국인']:+,.0f}  /  기관 {cum5['기관계']:+,.0f}  /  개인 {cum5['개인']:+,.0f}",
        f"<b>20일 누적</b> 외국인 {cum20['외국인']:+,.0f}  /  기관 {cum20['기관계']:+,.0f}  /  개인 {cum20['개인']:+,.0f}",
    ]

    if sp.exists():
        s = pd.read_parquet(sp)
        d_latest = s["date"].max()
        day = s[s["date"] == d_latest].copy()
        if not day.empty:
            day["foreign_value"] = day["foreign_net"] * day["close"] / 1e8  # 억원
            from config import WATCHLIST
            day["name"] = day["code"].map(WATCHLIST)
            top = day.nlargest(3, "foreign_value")[["name", "foreign_value"]]
            bot = day.nsmallest(3, "foreign_value")[["name", "foreign_value"]]
            lines += [
                "",
                f"<b>외국인 순매수 TOP3</b>",
                *[f"  {n}: {v:+,.0f}억" for n, v in zip(top["name"], top["foreign_value"])],
                f"<b>외국인 순매도 TOP3</b>",
                *[f"  {n}: {v:+,.0f}억" for n, v in zip(bot["name"], bot["foreign_value"])],
            ]

    url = os.environ.get("STREAMLIT_URL", "").strip()
    if url:
        lines += ["", f'<a href="{url}">→ 대시보드 열기</a>']
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str) -> dict:
    r = requests.post(
        TG_API.format(token=token),
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": False},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


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

    text = build_summary()
    if not pushed and "(no changes to commit)" not in text:
        text += "\n\n<i>(데이터 변경 없음 — 사이트 갱신 없음)</i>"

    print("  posting to Telegram ...")
    resp = send_telegram(tg_token, chat_id, text)
    ok = resp.get("ok", False)
    print(f"    telegram ok={ok}  message_id={resp.get('result', {}).get('message_id')}")
    if not ok:
        print(f"    response: {resp}")
        sys.exit(2)


if __name__ == "__main__":
    main()
