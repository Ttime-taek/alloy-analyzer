"""Re-verify compare tab, favorites, mobile layout via Playwright + Chrome CDP."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from qa_browser_common import (
    URL,
    ensure_elem_page,
    find_chrome,
    fresh_profile,
    free_cdp_port,
    pick_cdp_page,
    reset_ui_page,
    start_chrome,
    stop_chrome,
)

OUT_DIR = Path(__file__).resolve().parents[1] / ".gstack" / "qa-reports" / "screenshots"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: pip install playwright")
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict = {"checks": [], "screenshots": []}

    free_cdp_port()
    fresh_profile()
    proc = start_chrome(URL, find_chrome())
    time.sleep(5)

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = pick_cdp_page(browser)
            page.goto(URL, wait_until="networkidle", timeout=60000)
            page.set_default_timeout(20000)

            results["title"] = page.title()
            results["checks"].append({"id": "load", "ok": "합금" in page.title()})

            reset_ui_page(page)
            for el in ("Cu", "Bi"):
                ensure_elem_page(page, el)

            analyze_btn = page.get_by_role("button", name="분석")
            disabled = analyze_btn.is_disabled()
            total_text = page.locator("text=/조성 A 총합/").first.inner_text(timeout=3000)
            results["checks"].append(
                {
                    "id": "issue-002-button-disabled",
                    "ok": disabled,
                    "total_text": total_text,
                }
            )

            if not disabled:
                analyze_btn.click()
                time.sleep(1)
                err = page.locator("text=/오류:/").first.inner_text(timeout=3000)
                results["checks"].append(
                    {
                        "id": "issue-001-error-text",
                        "ok": "[object Object]" not in err,
                        "error_shown": err[:200],
                    }
                )

            page.screenshot(path=str(OUT_DIR / "reverify-desktop-0pct.png"), full_page=True)
            results["screenshots"].append("reverify-desktop-0pct.png")

            page.get_by_role("tab", name="비교 분석").click()
            time.sleep(0.5)
            compare_hint = page.locator("text=/조성 A와 B/").count() > 0
            results["checks"].append({"id": "compare-tab", "ok": compare_hint})
            page.screenshot(path=str(OUT_DIR / "reverify-compare-tab.png"), full_page=True)
            results["screenshots"].append("reverify-compare-tab.png")

            page.get_by_role("tab", name="단일 분석").click()
            fav_status = page.locator("text=/즐겨찾기/").first.inner_text(timeout=5000)
            fav_select = page.locator("select").filter(has=page.locator("option", has_text="불러오기"))
            has_fav_ui = fav_select.count() > 0 or "즐겨찾기" in fav_status
            results["checks"].append(
                {"id": "favorites-ui", "ok": has_fav_ui, "status_snippet": fav_status[:120]}
            )

            options = page.locator("select option").all_inner_texts()
            if len(options) > 2:
                for opt in options:
                    if opt and opt not in ("", "불러오기…", "원소 추가…"):
                        page.locator("select").first.select_option(label=opt)
                        break
                time.sleep(0.5)
                analyze_btn = page.get_by_role("button", name="분석")
                if analyze_btn.is_enabled():
                    analyze_btn.click()
                    page.wait_for_selector("text=분석 결과", timeout=60000)
                    results["checks"].append({"id": "favorite-analyze", "ok": True})
                else:
                    results["checks"].append(
                        {
                            "id": "favorite-analyze",
                            "ok": False,
                            "reason": "analyze still disabled after fav load",
                        }
                    )
            else:
                results["checks"].append(
                    {"id": "favorite-analyze", "ok": None, "reason": "no saved favorites to load"}
                )

            page.set_viewport_size({"width": 375, "height": 812})
            page.goto(URL, wait_until="networkidle")
            page.screenshot(path=str(OUT_DIR / "reverify-mobile.png"), full_page=True)
            results["screenshots"].append("reverify-mobile.png")
            mobile_overflow = page.evaluate(
                "() => document.documentElement.scrollWidth > window.innerWidth + 2"
            )
            results["checks"].append({"id": "mobile-layout", "ok": not mobile_overflow})

            browser.close()

        report_path = OUT_DIR.parent / "reverify-latest.json"
        report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(results, ensure_ascii=False, indent=2))
        failed = [c for c in results["checks"] if c.get("ok") is False]
        return 1 if failed else 0
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    finally:
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())
