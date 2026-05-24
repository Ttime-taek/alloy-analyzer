"""UI QA via Playwright CDP attach (system Chrome, no bundled launch)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from qa_browser_common import (
    CDP_ADDR,
    URL,
    find_chrome,
    fresh_profile,
    free_cdp_port,
    pick_cdp_page,
    run_composition_gate_check,
    start_chrome,
    stop_chrome,
)

OUT = Path(__file__).resolve().parents[1] / ".gstack" / "qa-reports" / "screenshots"


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    free_cdp_port()
    fresh_profile()
    proc = start_chrome(URL, find_chrome())
    time.sleep(5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://{CDP_ADDR}")
            page = pick_cdp_page(browser)
            page.goto(URL, wait_until="networkidle", timeout=90000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            page.screenshot(path=str(OUT / "home-cdp.png"), full_page=True)

            result = run_composition_gate_check(page, OUT, prefix="cdp")
            bundle = page.evaluate(
                """() => [...document.scripts].map(s => s.src).find(u => u && u.includes('/assets/index-')) || ''"""
            )
            result["bundle"] = bundle
            print(json.dumps(result, ensure_ascii=False, indent=2))
            browser.close()
            ok = result["analyze_disabled_at_99p5"] and result["analyze_enabled_at_100"]
            return 0 if ok else 2
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    finally:
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())
