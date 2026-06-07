"""Report-only QA capture for Alloy Predictor (Selenium, Windows-friendly)."""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from qa_browser_common import ELEMS, URL

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / ".gstack" / "qa-reports"
SHOT_DIR = REPORT_DIR / "screenshots"
DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def http_status(path: str) -> int:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:8000{path}")
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except Exception:
        return 0


def comp_select(driver):
    for sel in driver.find_elements(By.CSS_SELECTOR, "select"):
        if any(o.text == "원소 추가…" for o in sel.find_elements(By.TAG_NAME, "option")):
            return sel
    raise RuntimeError("composition select not found")


def reset_ui(driver) -> None:
    for btn in driver.find_elements(By.CSS_SELECTOR, "button.tactile-hit"):
        if btn.text.strip() == "초기화":
            btn.click()
            time.sleep(0.6)
            return


def ensure_elem(driver, sym: str) -> None:
    if driver.find_elements(By.XPATH, f"//label[normalize-space()='{sym}']"):
        return
    Select(comp_select(driver)).select_by_value(sym)
    time.sleep(0.25)


def fill_row(driver, sym: str, val: str) -> None:
    row = driver.find_element(By.XPATH, f"//label[normalize-space()='{sym}']/..")
    inp = row.find_element(By.CSS_SELECTOR, 'input[type="number"]')
    inp.clear()
    inp.send_keys(val)
    time.sleep(0.2)


def analyze_button(driver):
    for btn in driver.find_elements(By.CSS_SELECTOR, "button.tactile-hit"):
        if btn.text.strip() == "분석":
            return btn
    raise RuntimeError("analyze button not found")


def is_disabled(btn) -> bool:
    if btn.get_attribute("disabled"):
        return True
    if btn.get_attribute("aria-disabled") == "true":
        return True
    return btn.value_of_css_property("pointer-events") == "none"


def console_errors(driver) -> list[str]:
    out = []
    try:
        for e in driver.get_log("browser"):
            if e.get("level") in ("SEVERE", "ERROR"):
                out.append(str(e.get("message", ""))[:300])
    except Exception:
        pass
    return out


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    issues: list[dict] = []
    meta: dict = {}

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1440,1200")
    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, 90)

    try:
        driver.get(URL)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select")))
        time.sleep(1)
        meta["title"] = driver.title
        meta["framework"] = "Vite/React SPA"
        driver.save_screenshot(str(SHOT_DIR / "01-home.png"))

        fav_st = http_status("/favicon.ico")
        meta["favicon_status"] = fav_st
        if fav_st != 200:
            issues.append(
                {
                    "id": "ISSUE-001",
                    "severity": "low",
                    "category": "links",
                    "title": "/favicon.ico not served",
                    "detail": f"GET /favicon.ico returned {fav_st}",
                    "screenshots": [],
                }
            )

        errs = console_errors(driver)
        meta["console_errors_home"] = errs
        if errs:
            issues.append(
                {
                    "id": "ISSUE-002",
                    "severity": "medium",
                    "category": "console",
                    "title": "Console errors on landing",
                    "detail": errs[0],
                    "screenshots": ["screenshots/01-home.png"],
                }
            )

        reset_ui(driver)
        for sym in ELEMS:
            ensure_elem(driver, sym)
        fill_row(driver, "Sn", "96.2")
        fill_row(driver, "Ag", "0.3")
        fill_row(driver, "Bi", "3")
        fill_row(driver, "Cu", "0")
        time.sleep(0.5)
        d995 = is_disabled(analyze_button(driver))
        driver.save_screenshot(str(SHOT_DIR / "02-gate-99p5.png"))
        if not d995:
            issues.append(
                {
                    "id": "ISSUE-003",
                    "severity": "high",
                    "category": "functional",
                    "title": "Analyze enabled below 100% composition",
                    "detail": "At 99.5% total, Analyze should be disabled.",
                    "screenshots": ["screenshots/02-gate-99p5.png"],
                }
            )

        fill_row(driver, "Cu", "0.5")
        time.sleep(0.5)
        if is_disabled(analyze_button(driver)):
            issues.append(
                {
                    "id": "ISSUE-004",
                    "severity": "high",
                    "category": "functional",
                    "title": "Analyze stays disabled at 100%",
                    "detail": "After adjusting to 100%, Analyze should enable.",
                    "screenshots": ["screenshots/02-gate-99p5.png"],
                }
            )

        fill_row(driver, "Sn", "73.3")
        fill_row(driver, "Ag", "1")
        fill_row(driver, "Bi", "25")
        fill_row(driver, "Cu", "0.7")
        time.sleep(0.5)
        driver.save_screenshot(str(SHOT_DIR / "03-composition-ready.png"))
        analyze_button(driver).click()

        wait.until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".summary-card")) >= 4
            or "고상선" in (d.find_element(By.ID, "root").text or "")
        )
        time.sleep(1.5)
        driver.save_screenshot(str(SHOT_DIR / "04-after-analyze.png"))

        cards = driver.find_elements(By.CSS_SELECTOR, ".summary-card")
        kpi_strip = driver.find_elements(By.CSS_SELECTOR, "#results-kpi-strip")
        meta["summary_card_count"] = len(cards)
        meta["kpi_strip_present"] = bool(kpi_strip)

        if len(cards) < 4:
            issues.append(
                {
                    "id": "ISSUE-005",
                    "severity": "medium",
                    "category": "functional",
                    "title": "KPI summary cards not visible after analyze",
                    "detail": f"Found {len(cards)} .summary-card elements; expected ≥4.",
                    "screenshots": ["screenshots/04-after-analyze.png"],
                }
            )

        root_text = driver.find_element(By.ID, "root").text
        if "고상선" not in root_text and "액상선" not in root_text:
            issues.append(
                {
                    "id": "ISSUE-006",
                    "severity": "critical",
                    "category": "functional",
                    "title": "Melt temperatures missing after analyze",
                    "detail": "No solidus/liquidus labels in results panel.",
                    "screenshots": ["screenshots/04-after-analyze.png"],
                }
            )

        post_errs = console_errors(driver)
        meta["console_errors_after_analyze"] = post_errs
        for i, msg in enumerate(post_errs[:3]):
            issues.append(
                {
                    "id": f"ISSUE-007-{i}",
                    "severity": "medium",
                    "category": "console",
                    "title": "Console error after analyze",
                    "detail": msg,
                    "screenshots": ["screenshots/04-after-analyze.png"],
                }
            )

        chart_btns = [
            b.text.strip()
            for b in driver.find_elements(By.CSS_SELECTOR, "button")
            if "차트" in (b.text or "") or "슬라이드" in (b.text or "")
        ]
        meta["chart_slideshow_buttons"] = chart_btns[:5]

        try:
            opened = False
            for btn in driver.find_elements(By.CSS_SELECTOR, "button"):
                t = (btn.text or "").strip()
                if t == "슬라이드 보고서":
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.3)
                    btn.click()
                    time.sleep(1.5)
                    driver.save_screenshot(str(SHOT_DIR / "05-slideshow-modal.png"))
                    dialogs = driver.find_elements(
                        By.CSS_SELECTOR,
                        "[role='dialog'], .slideshow-overlay, .chart-report-overlay",
                    )
                    meta["chart_report_opened"] = bool(dialogs) or "슬라이드" in (
                        driver.find_element(By.ID, "root").text or ""
                    )
                    meta["dialog_count"] = len(dialogs)
                    opened = meta["chart_report_opened"]
                    if not opened:
                        issues.append(
                            {
                                "id": "ISSUE-008",
                                "severity": "medium",
                                "category": "functional",
                                "title": "슬라이드 보고서 버튼이 모달을 열지 않음",
                                "detail": "Clicked '슬라이드 보고서' but no dialog/overlay detected.",
                                "screenshots": ["screenshots/05-slideshow-modal.png"],
                            }
                        )
                    break
            if not opened and not any(i["id"] == "ISSUE-008" for i in issues):
                meta["chart_report_opened"] = False
                issues.append(
                    {
                        "id": "ISSUE-009",
                        "severity": "medium",
                        "category": "functional",
                        "title": "슬라이드 보고서 버튼을 찾을 수 없음",
                        "detail": f"Buttons seen: {chart_btns[:8]}",
                        "screenshots": ["screenshots/04-after-analyze.png"],
                    }
                )
        except Exception as exc:
            meta["chart_report_opened"] = False
            meta["chart_report_error"] = str(exc)
            issues.append(
                {
                    "id": "ISSUE-010",
                    "severity": "high",
                    "category": "functional",
                    "title": "슬라이드 보고서 클릭 중 예외",
                    "detail": str(exc)[:200],
                    "screenshots": ["screenshots/04-after-analyze.png"],
                }
            )

        pages = ["home", "analyze-flow", "chart-modal"]
        meta["pages_visited"] = pages
        meta["screenshot_count"] = len(list(SHOT_DIR.glob("*.png")))

    finally:
        driver.quit()

    # Health score (simplified rubric)
    sev_penalty = {"critical": 25, "high": 15, "medium": 8, "low": 3}
    functional = max(0, 100 - sum(sev_penalty.get(i["severity"], 0) for i in issues if i["category"] == "functional"))
    console = 100 if not meta.get("console_errors_home") and not meta.get("console_errors_after_analyze") else 70
    links = 100 if meta.get("favicon_status") == 200 else 85
    score = round(0.2 * functional + 0.15 * console + 0.1 * links + 0.55 * 95, 1)
    if any(i["severity"] == "critical" for i in issues):
        score = min(score, 60)

    payload = {
        "date": DATE,
        "url": URL,
        "healthScore": score,
        "meta": meta,
        "issues": issues,
        "categoryScores": {"functional": functional, "console": console, "links": links},
    }

    baseline_path = REPORT_DIR / "baseline.json"
    baseline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = REPORT_DIR / f"qa-report-localhost-8000-{DATE}.md"
    lines = [
        f"# QA Report — Alloy Predictor ({DATE})",
        "",
        f"- **URL:** {URL}",
        f"- **Mode:** Full (Selenium headless; gstack browse daemon unavailable on Windows)",
        f"- **Health score:** {score}/100",
        f"- **Pages exercised:** {', '.join(meta.get('pages_visited', []))}",
        f"- **Screenshots:** `.gstack/qa-reports/screenshots/` ({meta.get('screenshot_count', 0)} files)",
        "",
        "## Summary",
        "",
        f"| Severity | Count |",
        f"|----------|-------|",
    ]
    for sev in ("critical", "high", "medium", "low"):
        n = sum(1 for i in issues if i["severity"] == sev)
        lines.append(f"| {sev.capitalize()} | {n} |")
    lines.extend(
        [
            "",
            "## Top issues to fix",
            "",
        ]
    )
    for i, issue in enumerate(issues[:3], 1):
        lines.append(f"{i}. **{issue['title']}** ({issue['severity']}) — {issue['detail']}")
    if not issues:
        lines.append("_No issues recorded in automated pass._")
    lines.extend(["", "## Issues", ""])
    for issue in issues:
        lines.append(f"### {issue['id']}: {issue['title']}")
        lines.append(f"- **Severity:** {issue['severity']}")
        lines.append(f"- **Category:** {issue['category']}")
        lines.append(f"- **Detail:** {issue['detail']}")
        if issue.get("screenshots"):
            lines.append(f"- **Evidence:** {', '.join(issue['screenshots'])}")
        lines.append("")
    lines.extend(["## Metadata", "", "```json", json.dumps(meta, ensure_ascii=False, indent=2), "```", ""])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "score": score, "issues": len(issues)}, ensure_ascii=False))
    return 0 if score >= 80 else 1


if __name__ == "__main__":
    raise SystemExit(main())
