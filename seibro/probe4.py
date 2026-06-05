"""Probe 4: call goSearch() directly and capture the data fetch."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "probe_out"

TARGET = "https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/ovsSec/BIP_CNTS10013V.xml&menuNo=921"


def main():
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ko-KR", viewport={"width": 1600, "height": 1200})
        page = ctx.new_page()

        page.on("request", lambda r: "callServletService" in r.url and
                captured.append(("REQ", r.url, (r.post_data or "")[:3000])))
        page.on("response", lambda r: "callServletService" in r.url and
                captured.append(("RES", r.url, _safe_text(r))))

        page.goto(TARGET, wait_until="networkidle", timeout=60_000)
        time.sleep(4)

        before = len(captured)
        try:
            page.evaluate("goSearch()")
            print("called goSearch()")
        except Exception as e:
            print(f"goSearch() failed: {e}")
        time.sleep(6)
        after = len(captured)
        print(f"new events from goSearch: {after - before}")
        new = captured[before:]
        for i, (phase, url, body) in enumerate(new):
            print(f"\n--- {phase} #{i} ---")
            print(body[:1800])

        # Save full network log
        (OUT / "p4_network.json").write_text(
            json.dumps(captured, ensure_ascii=False, indent=2)[:200_000], encoding="utf-8"
        )

        browser.close()


def _safe_text(r):
    try:
        return r.text()[:5000]
    except Exception:
        return "<binary>"


if __name__ == "__main__":
    main()
