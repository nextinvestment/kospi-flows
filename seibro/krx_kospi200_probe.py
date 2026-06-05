"""Probe KRX 정보데이터시스템 for KOSPI200 investor flow.

Target: investor trading by KOSPI200 (대형주 묶음). Try several known KRX menu paths.
KRX has multiple menu IDs — try the ones for 투자자별 거래실적 (by stock index).
"""
from __future__ import annotations
import json
import time
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(__file__).parent / "probe_out"
OUT.mkdir(exist_ok=True)

URLS = [
    # 투자자별 거래실적 (개별 추이) — menuId=MDC0201020201 was MMC2... new path
    "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020201",
    # 코스피 200 시세
    "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101",
    # statistics main
    "http://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT02401.jsp",
]


def main():
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ko-KR", viewport={"width": 1600, "height": 1200})
        page = ctx.new_page()
        page.on("response", lambda r: captured.append((r.status, r.url[:200], _safe(r))) if any(k in r.url for k in ["MDC", "krx", "STAT"]) else None)

        for u in URLS:
            print(f"\n=== {u} ===")
            try:
                page.goto(u, wait_until="networkidle", timeout=30_000)
                time.sleep(3)
                # Find any table with KOSPI 200 data
                tables = page.evaluate("""
                    () => {
                        const out = [];
                        for (const t of document.querySelectorAll('table')) {
                            const rows = t.querySelectorAll('tr').length;
                            const cls = (t.className || '').toString();
                            const summ = (t.summary || '').slice(0, 60);
                            if (rows >= 2) out.push({rows, cls: cls.slice(0,60), summ});
                        }
                        return out.slice(0, 10);
                    }
                """)
                print(f"  tables: {tables}")
                # Capture page text fragments mentioning KOSPI 200
                text = page.evaluate("() => document.body.innerText.slice(0, 2000)")
                if "코스피 200" in text or "KOSPI 200" in text or "외국인" in text:
                    print(f"  text has K200/외국인 — relevant!")
                    print(f"  excerpt: {text[:500]}")
            except Exception as e:
                print(f"  failed: {e}")

        browser.close()


def _safe(r):
    try:
        return r.text()[:200]
    except Exception:
        return "<binary>"


if __name__ == "__main__":
    main()
