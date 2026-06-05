"""Probe SEIBRO: open page, capture network calls, save HTML + screenshot.

Goal: find the underlying XHR/fetch endpoint that returns the per-stock
foreign deposit settlement TOP-50 data, so we can hit it directly without
DOM scraping in production.
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

START_URL = "https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/index.xml"


def main():
    network_log = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            locale="ko-KR",
        )
        page = ctx.new_page()

        def on_request(req):
            if any(p in req.url for p in ["/websquare", "/process", "BIP_", "comm/json", "ajax", "xml"]):
                network_log.append({
                    "phase": "request",
                    "method": req.method,
                    "url": req.url[:200],
                    "post": (req.post_data or "")[:500] if req.post_data else None,
                })

        def on_response(resp):
            if any(p in resp.url for p in ["/websquare", "/process", "BIP_", "comm/json", "ajax", "xml"]):
                try:
                    body_preview = resp.text()[:500]
                except Exception:
                    body_preview = "<binary>"
                network_log.append({
                    "phase": "response",
                    "status": resp.status,
                    "url": resp.url[:200],
                    "body_preview": body_preview,
                })

        page.on("request", on_request)
        page.on("response", on_response)

        print("opening SEIBRO main…")
        page.goto(START_URL, wait_until="networkidle", timeout=60_000)
        time.sleep(2)

        # Save initial HTML + screenshot
        (OUT / "main.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(OUT / "main.png"), full_page=True)
        print(f"  saved main.html / main.png (page title: {page.title()})")

        # Try to find menu by visible Korean text
        # Top menu: 국제거래
        print("\nlooking for menu '국제거래' …")
        try:
            page.click("text=국제거래", timeout=10_000)
            time.sleep(1)
            print("  clicked 국제거래")
        except Exception as e:
            print(f"  ! couldn't click 국제거래: {e}")

        try:
            page.click("text=외화증권 예탁결제", timeout=10_000)
            time.sleep(1)
            print("  clicked 외화증권 예탁결제")
        except Exception as e:
            print(f"  ! couldn't click 외화증권 예탁결제: {e}")

        try:
            page.click("text=종목별", timeout=10_000)
            time.sleep(2)
            print("  clicked 종목별")
        except Exception as e:
            print(f"  ! couldn't click 종목별: {e}")

        # Wait for any XHR
        time.sleep(3)

        (OUT / "after_menu.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(OUT / "after_menu.png"), full_page=True)
        print(f"\nafter menu navigation:")
        print(f"  url: {page.url[:200]}")
        print(f"  saved after_menu.html / after_menu.png")

        # Dump network log
        (OUT / "network.json").write_text(
            json.dumps(network_log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  saved network.json ({len(network_log)} entries)")

        browser.close()

    # Summary of unique endpoints
    urls = sorted(set(e["url"] for e in network_log))
    print(f"\nunique request URLs ({len(urls)}):")
    for u in urls[:30]:
        print(f"  {u}")


if __name__ == "__main__":
    main()
