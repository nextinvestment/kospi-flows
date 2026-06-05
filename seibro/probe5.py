"""Probe 5: scan for any clickable WebSquare trigger near search criteria."""
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
                captured.append(("REQ", (r.post_data or "")[:3000])))
        page.on("response", lambda r: "callServletService" in r.url and
                captured.append(("RES", _safe(r))))

        page.goto(TARGET, wait_until="networkidle", timeout=60_000)
        time.sleep(6)

        # Dump all elements with id starting with 'group_btn' or having w2trigger class,
        # or input[type=button], or with onclick handler
        elements = page.evaluate("""
            () => {
                const out = [];
                const seen = new Set();
                const isClickable = (el) => {
                    if (el.tagName === 'BUTTON' || el.tagName === 'INPUT') return true;
                    if (el.onclick) return true;
                    const cls = (el.className || '').toString();
                    if (/w2trigger|btn|button/i.test(cls)) return true;
                    return false;
                };
                for (const el of document.querySelectorAll('*')) {
                    if (!isClickable(el)) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    if (rect.y < 100) continue;  // skip top menu
                    const txt = (el.innerText || el.value || el.title || '').trim().slice(0, 30);
                    const id = el.id || '';
                    const cls = (el.className || '').toString().slice(0, 80);
                    const key = `${id}|${cls}|${txt}`;
                    if (seen.has(key)) continue;
                    seen.add(key);
                    out.push({
                        tag: el.tagName, id, cls, txt,
                        x: Math.round(rect.x), y: Math.round(rect.y),
                        w: Math.round(rect.width), h: Math.round(rect.height),
                    });
                }
                return out;
            }
        """)
        # Print elements between search bar (y ~ 300-350) and grid header
        print(f"all clickable elements below header ({len(elements)}):")
        for e in elements:
            if 280 < e["y"] < 450:
                print(f"  {e}")

        # Also list every input[type=button|submit]
        inputs = page.evaluate("""
            () => {
                const r = [];
                for (const el of document.querySelectorAll('input[type=button],input[type=submit],a[onclick],div[onclick]')) {
                    const rect = el.getBoundingClientRect();
                    r.push({
                        tag: el.tagName, type: el.type, id: el.id,
                        cls: (el.className||'').slice(0,80),
                        value: el.value || el.innerText.slice(0,40),
                        x: Math.round(rect.x), y: Math.round(rect.y),
                    });
                }
                return r;
            }
        """)
        print(f"\nbutton-like inputs ({len(inputs)}):")
        for i in inputs[:30]:
            print(f"  {i}")

        # WebSquare buttons frequently have id starting with 'group_btn' or end with '_btn'
        # Try clicking by id pattern
        for candidate_id in page.evaluate("""
            () => Array.from(document.querySelectorAll('[id]'))
                .map(e => e.id)
                .filter(id => /btn|search|inquir|qry/i.test(id) && id.length < 50)
        """):
            print(f"  candidate id: {candidate_id}")

        browser.close()


def _safe(r):
    try:
        return r.text()[:3000]
    except Exception:
        return "<binary>"


if __name__ == "__main__":
    main()
