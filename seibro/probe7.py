"""Probe 7: strong click on search anchor."""
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

        # Inspect group186 in detail
        info = page.evaluate("""
            () => {
                const el = document.getElementById('group186');
                if (!el) return null;
                return {
                    tag: el.tagName,
                    outerHTML: el.outerHTML.slice(0, 500),
                    childCount: el.children.length,
                    childHTML: Array.from(el.children).map(c => c.outerHTML.slice(0,200))
                };
            }
        """)
        print("group186 info:")
        print(json.dumps(info, ensure_ascii=False, indent=2))

        before = len(captured)
        # Try Playwright's native click with force
        try:
            page.locator("#group186").click(force=True, timeout=8000)
            print("\nPlaywright force click on #group186")
        except Exception as e:
            print(f"  force click failed: {e}")

        time.sleep(5)
        new = captured[before:]
        print(f"new events: {len(new)}")
        if not new:
            # Try dispatch all kinds of events
            print("\ntrying dispatchEvent(click/mousedown/mouseup)...")
            page.evaluate("""
                () => {
                    const el = document.getElementById('group186');
                    if (!el) return;
                    for (const ev of ['mousedown','mouseup','click']) {
                        el.dispatchEvent(new MouseEvent(ev, {bubbles: true, cancelable: true, view: window}));
                    }
                    // Also try clicking children
                    for (const c of el.children) {
                        c.click();
                    }
                }
            """)
            time.sleep(5)
            new = captured[before:]
            print(f"after dispatch: {len(new)} new events")

        # Print latest events
        for i, (phase, body) in enumerate(new[-6:]):
            print(f"\n--- {phase} ---")
            print(body[:2500])

        browser.close()


def _safe(r):
    try:
        return r.text()[:5000]
    except Exception:
        return "<binary>"


if __name__ == "__main__":
    main()
