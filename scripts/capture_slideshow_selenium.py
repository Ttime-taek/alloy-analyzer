"""Capture slideshow slides 2-6 via Selenium + Edge (no Playwright browser bundle)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import sys as _sys

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT / "scripts"))

from qa_browser_common import URL as BASE_URL  # noqa: E402

URL = f"{BASE_URL}?slideVerify={int(time.time())}"

OUT = _ROOT / ".gstack" / "slide-verify-20260526"
COMP = {"Sn": "73.3", "Ag": "1", "Bi": "25", "Cu": "0.7"}


def dismiss_alerts(driver) -> None:
    for _ in range(3):
        try:
            alert = driver.switch_to.alert
            alert.dismiss()
            time.sleep(0.2)
        except Exception:
            break


def reset_ui(driver, wait: WebDriverWait) -> None:
    for btn in driver.find_elements(By.XPATH, "//button[normalize-space()='초기화']"):
        if btn.is_displayed():
            btn.click()
            time.sleep(0.6)
            return


def ensure_elem_row(driver, sym: str) -> None:
    if driver.find_elements(
        By.XPATH, f"//label[normalize-space()='{sym}']/..//input[@type='number']"
    ):
        return
    selects = driver.find_elements(By.TAG_NAME, "select")
    for sel_el in selects:
        opts = [o.text for o in sel_el.find_elements(By.TAG_NAME, "option")]
        if any("원소 추가" in t for t in opts):
            Select(sel_el).select_by_value(sym)
            time.sleep(0.3)
            return
    raise RuntimeError(f"원소 추가 select not found for {sym}")


def fill_wt(driver, sym: str, val: str) -> None:
    inp = driver.find_element(
        By.XPATH,
        f"//label[normalize-space()='{sym}']/..//input[@type='number']",
    )
    driver.execute_script(
        """
        const el = arguments[0];
        const v = arguments[1];
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(el, v);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        inp,
        val,
    )
    time.sleep(0.2)


def read_block_reason(driver) -> str:
    for el in driver.find_elements(By.CSS_SELECTOR, "[role='status']"):
        txt = (el.text or "").strip()
        if txt:
            return txt
    return ""


def read_error_alert(driver) -> str:
    for el in driver.find_elements(By.CSS_SELECTOR, "p[role='alert']"):
        txt = (el.text or "").strip()
        if txt and "입력" not in txt[:20]:
            return txt
    return ""


def expand_result_panel(driver) -> None:
    for btn in driver.find_elements(
        By.XPATH, "//button[contains(normalize-space(.), '분석 결과 펼치기')]"
    ):
        if btn.is_displayed():
            btn.click()
            time.sleep(0.4)
            return


def wait_for_slideshow_button(driver, timeout: int = 90):
    end = time.time() + timeout
    while time.time() < end:
        dismiss_alerts(driver)
        expand_result_panel(driver)
        for btn in driver.find_elements(By.TAG_NAME, "button"):
            label = (btn.text or "").strip()
            if ("슬라이드" in label and "보고서" in label) and btn.is_displayed():
                return btn
        err = read_error_alert(driver)
        if err and "분석 중" not in err:
            raise RuntimeError(err)
        if not driver.find_elements(By.CSS_SELECTOR, ".btn-spinner"):
            time.sleep(0.5)
        else:
            time.sleep(1)
    labels = [
        (b.text or "").strip()
        for b in driver.find_elements(By.TAG_NAME, "button")
        if (b.text or "").strip()
    ]
    raise TimeoutError(
        "슬라이드 보고서 button not found after analyze; buttons="
        + repr(labels[:25])
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"checks": [], "slides": [], "stage": "init"}

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1440,960")
    opts.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, 120)

    try:
        report["stage"] = "goto"
        driver.get(URL)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button")))
        report["stage"] = "page-ready"
        dismiss_alerts(driver)
        reset_ui(driver, wait)

        for sym in COMP:
            ensure_elem_row(driver, sym)
        for el, val in COMP.items():
            fill_wt(driver, el, val)

        report["stage"] = "filled-composition"
        analyze = driver.find_element(
            By.XPATH,
            "//button[normalize-space()='분석' and not(contains(., '중'))]",
        )
        try:
            WebDriverWait(driver, 20).until(
                lambda d: analyze.is_enabled() and analyze.value_of_css_property("opacity") != "0.65"
            )
        except Exception:
            report["error"] = read_block_reason(driver) or "analyze button stayed disabled"
            driver.save_screenshot(str(OUT / "debug-analyze-blocked.png"))
            raise
        report["stage"] = "analyze-click"
        analyze.click()
        report["stage"] = "wait-spinner"
        WebDriverWait(driver, 180).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".btn-spinner")) == 0
        )

        report["stage"] = "wait-slideshow-button"
        slide_btn = wait_for_slideshow_button(driver, timeout=120)
        report["stage"] = "open-slideshow"
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", slide_btn
        )
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", slide_btn)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".report-slideshow"))
        )
        time.sleep(0.5)

        report["stage"] = "slideshow-open"
        overflow = driver.execute_script("return document.body.style.overflow")
        report["checks"].append(
            {"id": "DR-001-scroll-lock", "ok": overflow == "hidden", "value": overflow}
        )

        dots = driver.find_elements(By.CSS_SELECTOR, ".rs-deck__dot")
        total = len(dots)
        report["checks"].append({"id": "slide-count", "ok": total >= 6, "count": total})

        frame = driver.find_element(By.CSS_SELECTOR, ".report-slideshow__frame")
        # Capture all slides (1..N) so we can spot missing data.
        for slide_num in range(1, total + 1):
            dots[slide_num - 1].click()
            time.sleep(0.45)
            meta = driver.execute_script(
                """
                const d = document.querySelector('.rs-deck');
                const label = d?.querySelector('.rs-kpi__label');
                const ls = label ? getComputedStyle(label) : null;
                const prog = d?.querySelector('.rs-deck__progress-fill');
                return {
                  eyebrow: d?.querySelector('.rs-chrome__eyebrow')?.textContent?.trim(),
                  title: d?.querySelector('.rs-chrome__title')?.textContent?.trim(),
                  kpiFont: ls?.fontSize,
                  kpiTransform: ls?.textTransform,
                  progressBg: prog ? getComputedStyle(prog).backgroundImage : null,
                };
                """
            )
            report["slides"].append({"slide": slide_num, **meta})
            frame.screenshot(str(OUT / f"slide-{slide_num:02d}-after.png"))

        eyebrows = [s.get("eyebrow") for s in report["slides"]]
        report["checks"].append(
            {"id": "DR-012-eyebrow-varies", "ok": len(set(eyebrows)) >= 3, "eyebrows": eyebrows}
        )
        kpi_ok = all(
            s.get("kpiFont") == "12px" and (s.get("kpiTransform") or "none") == "none"
            for s in report["slides"]
            if s.get("kpiFont")
        )
        report["checks"].append({"id": "DR-007-kpi-labels", "ok": kpi_ok})
        prog_ok = all(
            "gradient" not in (s.get("progressBg") or "").lower() for s in report["slides"]
        )
        report["checks"].append({"id": "DR-009-progress-solid", "ok": prog_ok})

        driver.find_element(By.TAG_NAME, "body").send_keys("\ue00c")  # Escape
        time.sleep(0.3)
        after = driver.execute_script("return document.body.style.overflow")
        report["checks"].append(
            {"id": "DR-001-scroll-restored", "ok": after != "hidden", "value": after}
        )
    except Exception as exc:
        report["error"] = str(exc)
        try:
            driver.save_screenshot(str(OUT / "debug-failure.png"))
        except Exception:
            pass
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    (OUT / "verify-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    failed = [c for c in report.get("checks", []) if c.get("ok") is False]
    return 1 if failed or report.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
