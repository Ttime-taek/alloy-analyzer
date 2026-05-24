"""Browser QA for composition 100% gate (Playwright + system Chrome CDP)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from qa_browser_common import (
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
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"error": "playwright not installed"}, ensure_ascii=False))
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    free_cdp_port()
    fresh_profile()
    proc = start_chrome(URL, find_chrome())
    time.sleep(5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = pick_cdp_page(browser)
            page.goto(URL, wait_until="networkidle", timeout=90000)
            page.screenshot(path=str(OUT / "home.png"), full_page=True)

            result = run_composition_gate_check(page, OUT)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            browser.close()

            if not result["analyze_disabled_at_99p5"]:
                return 2
            if not result["analyze_enabled_at_100"]:
                return 2
            return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    finally:
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())
