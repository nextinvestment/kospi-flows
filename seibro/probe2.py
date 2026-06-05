"""Probe SEIBRO ovsSec/BIP_CNTS10013V — settle by stock TOP50 page.

Navigate to the page, capture all network calls (esp. callServletService.jsp).
Try to trigger the search button and see what payload/response comes back.
"""
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
        )
        page = ctx.new_page()

        def on_request(req):
            if "callServletService" in req.url:
                captured.append({
                    "phase": "REQ",
                    "url": req.url,
                    "method": req.method,
                    "post": req.post_data,
                    "headers": {k: v for k, v in req.headers.items() if k.lower() in ("content-type", "submissionid")},
                })

        def on_response(resp):
            if "callServletService" in resp.url:
                try:
                    body = resp.text()
                except Exception:
                    body = "<binary>"
                captured.append({
                    "phase": "RES",
                    "status": resp.status,
                    "url": resp.url,
                    "body_chars": len(body),
                    "body_preview": body[:1500],
                })

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"opening {TARGET}")
        page.goto(TARGET, wait_until="networkidle", timeout=60_000)
        time.sleep(3)

        (OUT / "p2_initial.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(OUT / "p2_initial.png"), full_page=True)
        print(f"  title: {page.title()}")

        # Print visible buttons/links to find the search trigger
        buttons_info = page.evaluate("""
            () => {
                const out = [];
                for (const el of document.querySelectorAll('button, input[type=button], input[type=submit], a, [class*=btn]')) {
                    const txt = (el.innerText || el.value || '').trim();
                    if (txt && txt.length < 50) out.push({ tag: el.tagName, text: txt, id: el.id, cls: el.className.slice(0,80) });
                }
                return out.slice(0, 60);
            }
        """)
        print(f"\nvisible clickable elements ({len(buttons_info)}):")
        for b in buttons_info:
            if any(k in b["text"] for k in ["조회", "검색", "찾기", "Search"]):
                print(f"  ★ {b}")
            else:
                pass  # noisy

        # All texts containing 조회
        candidates = [b for b in buttons_info if "조회" in b["text"]]
        print(f"\n조회 candidates: {len(candidates)}")
        for c in candidates[:5]:
            print(f"  {c}")

        # Try clicking the first 조회 button
        try:
            page.click("text=조회", timeout=8000)
            print("  → clicked 조회")
            time.sleep(4)  # wait for XHR
        except Exception as e:
            print(f"  ! click 조회 failed: {e}")

        (OUT / "p2_after_search.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(OUT / "p2_after_search.png"), full_page=True)

        # Save captured network log
        (OUT / "p2_network.json").write_text(
            json.dumps(captured, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\ncaptured {len(captured)} callServletService events")
        for i, e in enumerate(captured):
            if e["phase"] == "REQ":
                print(f"\n--- REQ {i} ---")
                print(f"  URL : {e['url']}")
                print(f"  post: {(e.get('post') or '')[:400]}")
            else:
                print(f"--- RES {i}  status={e['status']}  body_chars={e['body_chars']} ---")
                print(f"  preview: {e['body_preview'][:400]}")

        browser.close()


if __name__ == "__main__":
    main()
