"""Probe 3: deeply inspect the SEIBRO page DOM + iframes + JS handlers."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "probe_out"
OUT.mkdir(exist_ok=True)

TARGET = "https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/ovsSec/BIP_CNTS10013V.xml&menuNo=921"


def main():
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            locale="ko-KR",
            viewport={"width": 1600, "height": 1200},
        )
        page = ctx.new_page()

        def on_req(req):
            if "callServletService" in req.url:
                captured.append(("REQ", req.method, (req.post_data or "")[:1500]))

        def on_res(resp):
            if "callServletService" in resp.url:
                try:
                    body = resp.text()
                except Exception:
                    body = "<binary>"
                captured.append(("RES", resp.status, body[:2000]))

        page.on("request", on_req)
        page.on("response", on_res)

        page.goto(TARGET, wait_until="networkidle", timeout=60_000)
        time.sleep(5)  # let WebSquare finish

        # Frames
        print(f"frames: {len(page.frames)}")
        for f in page.frames:
            print(f"  - {f.name!r} url={f.url[:120]}")

        # All clickable elements containing 조회 or 검색
        for f in page.frames:
            try:
                hits = f.evaluate("""
                    () => {
                        const r = [];
                        const all = document.querySelectorAll('*');
                        for (const el of all) {
                            const txt = (el.innerText || el.value || '').trim();
                            if (!txt) continue;
                            if (txt.length > 30) continue;
                            if (/조회|검색|search/i.test(txt)) {
                                const rect = el.getBoundingClientRect();
                                r.push({
                                    tag: el.tagName,
                                    txt: txt.slice(0,40),
                                    id: el.id,
                                    cls: el.className.toString().slice(0,80),
                                    visible: rect.width > 0 && rect.height > 0,
                                    x: Math.round(rect.x), y: Math.round(rect.y),
                                    w: Math.round(rect.width), h: Math.round(rect.height),
                                    onclick: !!el.onclick,
                                });
                            }
                        }
                        return r;
                    }
                """)
                if hits:
                    print(f"\nframe {f.name!r} '조회/검색' elements ({len(hits)}):")
                    for h in hits:
                        print(f"  {h}")
            except Exception as e:
                print(f"  frame eval failed: {e}")

        # Try to find a globally-defined search/submit function and call it
        for f in page.frames:
            try:
                globals_with_search = f.evaluate("""
                    () => {
                        const names = [];
                        for (const k in window) {
                            if (typeof window[k] === 'function' &&
                                /search|inquir|select|find|qry/i.test(k) &&
                                k.length < 40) {
                                names.push(k);
                            }
                        }
                        return names.slice(0, 30);
                    }
                """)
                if globals_with_search:
                    print(f"\nframe {f.name!r} fn candidates: {globals_with_search}")
            except Exception:
                pass

        # Snapshot page
        (OUT / "p3.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(OUT / "p3.png"), full_page=True)

        # Try force-clicking the first 조회 element via JS in main frame
        try:
            page.evaluate("""
                () => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const txt = (el.innerText || el.value || '').trim();
                        if (txt === '조회' || txt === '검색') {
                            el.click();
                            return el.outerHTML.slice(0, 200);
                        }
                    }
                    return 'no match';
                }
            """)
            print("\nforced JS-click on 조회/검색")
            time.sleep(5)
        except Exception as e:
            print(f"force click failed: {e}")

        # See if data XHR fired
        print(f"\ncallServletService events captured: {len(captured)}")
        data_responses = [c for c in captured if c[0] == "RES" and "result=" in c[2] and 'value=' in c[2]]
        # Print last few RES bodies that look like data (not menu/auth)
        for i, c in enumerate(captured[-6:]):
            phase, st_or_method, body = c
            print(f"--- {phase} ({st_or_method}) ---")
            print(body[:600])
            print()

        browser.close()


if __name__ == "__main__":
    main()
