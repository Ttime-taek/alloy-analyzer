"""Browser + API QA smoke for local and deployed alloy analyzer targets.

Usage examples:
  py -3 scripts\\qa_reverify_playwright.py --label local
  py -3 scripts\\qa_reverify_playwright.py --label deploy ^
      --base-url https://alloy-analyzer.vercel.app/ ^
      --api-url https://alloy-analyzer.onrender.com
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from qa_browser_common import find_chrome, free_cdp_port, fresh_profile, pick_cdp_page, start_chrome, stop_chrome

OUT_DIR = Path(__file__).resolve().parents[1] / ".gstack" / "qa-reports"
SCREENSHOT_DIR = OUT_DIR / "screenshots"

SINGLE_FAVORITE_CANDIDATES = ["48", "90", "86", "22"]
COMPARE_FAVORITE_A = "48"
COMPARE_FAVORITE_B = "92"
API_CASES = [
    {
        "id": "api-sac305",
        "payload": {"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}},
        "expect_status": 200,
        "expect_best_name": "Sn3.0Ag0.5Cu",
    },
    {
        "id": "api-p-ni",
        "payload": {"comp": {"Sn": 99.455, "Cu": 0.5, "Ni": 0.03, "P": 0.015}},
        "expect_status": 200,
        "expect_best_name": "Sn-0.5Cu-0.03Ni-0.015P",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="local")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    return parser.parse_args()


def json_request(url: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def click_button_by_text(page, text: str) -> bool:
    return bool(
        page.evaluate(
            """(wanted) => {
                const buttons = [...document.querySelectorAll("button")];
                const btn = buttons.find((node) => (node.textContent || "").trim() === wanted);
                if (!btn) return false;
                btn.click();
                return true;
            }""",
            text,
        )
    )


def is_analyze_enabled(page) -> bool:
    return bool(
        page.evaluate(
            """() => {
                const buttons = [...document.querySelectorAll("button")];
                const btn = buttons.find((node) => (node.textContent || "").trim() === "분석");
                return Boolean(btn && !btn.disabled);
            }"""
        )
    )


def click_analyze(page) -> bool:
    return click_button_by_text(page, "분석")


def visible_favorite_selects(page, labels: list[str]) -> list[dict]:
    return page.locator("select").evaluate_all(
        """(nodes, wanted) =>
        nodes
          .map((node, index) => {
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return {
              index,
              visible: style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0,
              options: [...node.options].map((opt) => (opt.textContent || "").trim()),
            };
          })
          .filter((entry) => entry.visible && entry.options.some((label) => wanted.includes(label)))
        """,
        labels,
    )


def wait_for_analysis_result(page, compare: bool = False) -> None:
    if compare:
        page.wait_for_selector("text=/B-A|B−A/", timeout=60000)
    else:
        page.wait_for_selector("text=분석 결과", timeout=60000)


def screenshot_path(label: str, name: str) -> str:
    return str((SCREENSHOT_DIR / f"{label}-{name}.png").resolve())


def run_api_checks(api_url: str) -> list[dict]:
    checks: list[dict] = []
    status, about = json_request(f"{api_url}/api/about")
    checks.append(
        {
            "id": "api-about",
            "ok": status == 200,
            "status": status,
            "gemini": bool((about.get("runtime") or {}).get("gemini_configured")),
            "cerebras": bool((about.get("runtime") or {}).get("cerebras_configured")),
        }
    )
    status, favorites = json_request(f"{api_url}/api/favorites")
    favs = favorites.get("favorites") if isinstance(favorites, dict) else None
    checks.append(
        {
            "id": "api-favorites",
            "ok": status == 200 and isinstance(favs, list) and len(favs) > 0,
            "status": status,
            "storage": favorites.get("storage") if isinstance(favorites, dict) else None,
            "count": len(favs or []),
        }
    )
    for case in API_CASES:
        status, payload = json_request(f"{api_url}/api/analyze", method="POST", payload=case["payload"])
        checks.append(
            {
                "id": case["id"],
                "ok": status == case["expect_status"]
                and (payload.get("best_name") == case["expect_best_name"] if isinstance(payload, dict) else False),
                "status": status,
                "best_name": payload.get("best_name") if isinstance(payload, dict) else None,
            }
        )
    return checks


def run_browser_checks(base_url: str, label: str) -> tuple[list[dict], list[str]]:
    from playwright.sync_api import sync_playwright

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []
    screenshots: list[str] = []

    proc = None
    free_cdp_port()
    fresh_profile()
    try:
        proc = start_chrome(base_url, find_chrome())
        time.sleep(5)
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = pick_cdp_page(browser, url_fragment="")
            page.goto(base_url, wait_until="networkidle", timeout=60000)
            page.set_default_timeout(20000)

            checks.append({"id": "page-load", "ok": "AI" in page.title(), "title": page.title()})

            click_button_by_text(page, "단일 분석")
            body_text = page.locator("body").inner_text()
            single_selects = visible_favorite_selects(page, SINGLE_FAVORITE_CANDIDATES + [COMPARE_FAVORITE_B])
            checks.append({"id": "single-favorites-ui", "ok": bool(single_selects), "body_hint": body_text[:120]})
            if single_selects:
                single_target = single_selects[0]
                pick = next((opt for opt in SINGLE_FAVORITE_CANDIDATES if opt in single_target["options"]), None)
                if pick:
                    page.locator("select").nth(single_target["index"]).select_option(label=pick)
                    page.wait_for_timeout(900)
                    enabled = is_analyze_enabled(page)
                    checks.append({"id": "single-favorite-enabled", "ok": enabled, "favorite": pick})
                    if enabled and click_analyze(page):
                        wait_for_analysis_result(page, compare=False)
                        page.screenshot(path=screenshot_path(label, "single-favorite"), full_page=True)
                        screenshots.append(f"{label}-single-favorite.png")
                        checks.append({"id": "single-favorite-result", "ok": True, "favorite": pick})
                    else:
                        checks.append({"id": "single-favorite-result", "ok": False, "favorite": pick})

            click_button_by_text(page, "비교 분석")
            page.wait_for_timeout(700)
            checks.append(
                {
                    "id": "compare-tab",
                    "ok": bool(
                        page.locator("text=조성 A").count()
                        and page.locator("text=조성 B").count()
                        and page.locator("text=A 즐겨찾기").count()
                        and page.locator("text=B 즐겨찾기").count()
                    ),
                }
            )
            page.screenshot(path=screenshot_path(label, "compare-tab"), full_page=True)
            screenshots.append(f"{label}-compare-tab.png")

            compare_selects = visible_favorite_selects(page, [COMPARE_FAVORITE_A, COMPARE_FAVORITE_B] + SINGLE_FAVORITE_CANDIDATES)
            if len(compare_selects) >= 2:
                page.locator("select").nth(compare_selects[0]["index"]).select_option(label=COMPARE_FAVORITE_A)
                page.locator("select").nth(compare_selects[1]["index"]).select_option(label=COMPARE_FAVORITE_B)
                page.wait_for_timeout(900)
                enabled = is_analyze_enabled(page)
                checks.append({"id": "compare-favorite-enabled", "ok": enabled})
                if enabled and click_analyze(page):
                    wait_for_analysis_result(page, compare=True)
                    page.screenshot(path=screenshot_path(label, "compare-result"), full_page=True)
                    screenshots.append(f"{label}-compare-result.png")
                    checks.append({"id": "compare-favorite-result", "ok": True})
                else:
                    checks.append({"id": "compare-favorite-result", "ok": False})
            else:
                checks.append({"id": "compare-favorite-result", "ok": False, "reason": "compare selects missing"})

            page.set_viewport_size({"width": 375, "height": 812})
            page.goto(base_url, wait_until="networkidle", timeout=60000)
            page.screenshot(path=screenshot_path(label, "mobile"), full_page=True)
            screenshots.append(f"{label}-mobile.png")
            checks.append(
                {
                    "id": "mobile-layout",
                    "ok": not page.evaluate(
                        "() => document.documentElement.scrollWidth > window.innerWidth + 2"
                    ),
                }
            )
            browser.close()
    finally:
        stop_chrome(proc)

    return checks, screenshots


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {
        "label": args.label,
        "base_url": args.base_url,
        "api_url": args.api_url,
        "checks": [],
        "screenshots": [],
    }

    try:
        results["checks"].extend(run_api_checks(args.api_url))
        browser_checks, screenshots = run_browser_checks(args.base_url, args.label)
        results["checks"].extend(browser_checks)
        results["screenshots"].extend(screenshots)
    except Exception as exc:
        results["checks"].append({"id": "script-error", "ok": False, "error": str(exc)})

    report_path = OUT_DIR / f"qa-smoke-{args.label}.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    failed = [item for item in results["checks"] if item.get("ok") is False]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
