"""Probe 6: click the search button (#group186) and capture the data response."""
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
                captured.append(("REQ", (r.post_data or "")[:3500])))
        page.on("response", lambda r: "callServletService" in r.url and
                captured.append(("RES", _safe(r))))

        page.goto(TARGET, wait_until="networkidle", timeout=60_000)
        time.sleep(5)

        before = len(captured)
        # Click the search anchor by id
        try:
            page.evaluate("document.getElementById('group186').click()")
            print("clicked #group186 via JS")
        except Exception as e:
            print(f"  click failed: {e}")
        time.sleep(8)
        new = captured[before:]
        print(f"\nnew callServlet events after click: {len(new)}")
        for i, (phase, body) in enumerate(new):
            print(f"\n--- {phase} #{i} ---")
            print(body[:2500])

        (OUT / "p6_network.json").write_text(
            json.dumps(captured, ensure_ascii=False, indent=2)[:300_000], encoding="utf-8"
        )
        browser.close()


def _safe(r):
    try:
        return r.text()[:5000]
    except Exception:
        return "<binary>"


if __name__ == "__main__":
    main()
