"""DEPRECATED. Functionality merged into ../stock-screener/market_bot.exe.

The new bot still responds to the same triggers (업데이트, 갱신, update, refresh,
지금) AND adds slash commands (/pulse /futures /options /etf /seohak /all).

Do not run this file. start_bot.bat / stop_bot.bat now manage market_bot.exe.
"""
import sys
sys.stderr.write(
    "kospi-flows/telegram_bot.py is deprecated.\n"
    "Use ../stock-screener/market_bot.exe instead.\n"
)
sys.exit(1)


_LEGACY_DOCSTRING = """  # noqa: keep original behaviour archived below
Long-poll Telegram bot — listens for trigger keywords and runs ingest+notify.

Triggers (case-insensitive substring match in incoming chat text):
  업데이트, 갱신, update, /update, refresh, /refresh, now

Behaviour:
  1. ack with "🔄 업데이트 시작합니다…" so the user knows it's working
  2. run `python run_daily.py` (fresh fetch from Naver, ~90s)
  3. run `python push_and_notify.py` (git push + summary messages)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent


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


load_env()
TOKEN = os.environ["TG_BOT_TOKEN"]
CHAT_ID = int(os.environ["TG_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"

TRIGGERS = ["업데이트", "갱신", "update", "/update", "refresh", "/refresh", " now", "지금"]


def send(text: str):
    try:
        requests.post(
            f"{API}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
    except Exception as e:
        print(f"  ! ack send failed: {e}")


def matches(text: str) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in TRIGGERS)


def handle(trigger_text: str):
    print(f"  [{time.strftime('%H:%M:%S')}] triggered by: {trigger_text!r}")
    send("🔄 업데이트 시작합니다… (~90초)")
    t0 = time.time()
    try:
        # Fresh fetch from Naver (195 stocks + KOSPI market + index)
        subprocess.run([sys.executable, str(HERE / "run_daily.py")],
                       cwd=HERE, check=False, timeout=300)
        # Build + send summary
        subprocess.run([sys.executable, str(HERE / "push_and_notify.py")],
                       cwd=HERE, check=False, timeout=120)
        print(f"  done in {time.time() - t0:.1f}s")
    except subprocess.TimeoutExpired:
        send("⚠️ 업데이트 타임아웃 (5분 초과). 로그를 확인하세요.")
    except Exception as e:
        send(f"⚠️ 업데이트 실패: {e}")
        print(f"  ! handle failed: {e}")


def get_initial_offset() -> int:
    """Skip all messages older than now so we don't re-trigger on startup."""
    try:
        r = requests.get(f"{API}/getUpdates", params={"offset": -1, "timeout": 1}, timeout=10)
        items = r.json().get("result", [])
        if items:
            return items[-1]["update_id"] + 1
    except Exception:
        pass
    return 0


def main():
    print(f"Listening on chat {CHAT_ID} (triggers: {TRIGGERS})")
    offset = get_initial_offset()
    print(f"  starting offset: {offset}")
    while True:
        try:
            r = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 30, "allowed_updates": ["message", "channel_post"]},
                timeout=40,
            )
            data = r.json()
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("channel_post") or {}
                chat = msg.get("chat", {})
                if chat.get("id") != CHAT_ID:
                    continue
                text = msg.get("text", "") or ""
                if matches(text):
                    handle(text)
        except requests.exceptions.ReadTimeout:
            pass  # long-poll normal timeout
        except Exception as e:
            print(f"poll error: {e}, sleeping 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
