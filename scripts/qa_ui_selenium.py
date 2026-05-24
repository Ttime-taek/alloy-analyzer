"""UI QA via Selenium + Chrome remote debugging (no Playwright driver)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from qa_browser_common import (
    CDP_ADDR,
    ELEMS,
    URL,
    find_chrome,
    fresh_profile,
    free_cdp_port,
    start_chrome,
    stop_chrome,
)

OUT = Path(__file__).resolve().parents[1] / ".gstack" / "qa-reports" / "screenshots"


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


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    free_cdp_port()
    fresh_profile()
    proc = start_chrome(URL, find_chrome())
    time.sleep(5)

    opts = Options()
    opts.add_experimental_option("debuggerAddress", CDP_ADDR)
    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, 30)

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select")))
        driver.get(URL)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select")))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        reset_ui(driver)
        driver.save_screenshot(str(OUT / "home-selenium.png"))

        for sym in ELEMS:
            ensure_elem(driver, sym)

        fill_row(driver, "Sn", "96.2")
        fill_row(driver, "Ag", "0.3")
        fill_row(driver, "Bi", "3")
        fill_row(driver, "Cu", "0")
        time.sleep(0.6)
        driver.save_screenshot(str(OUT / "composition-99p5-selenium.png"))

        d995 = is_disabled(analyze_button(driver))
        block = driver.find_elements(By.CSS_SELECTOR, "[role='status']")
        block_text = block[0].text if block else ""

        fill_row(driver, "Cu", "0.5")
        time.sleep(0.6)
        driver.save_screenshot(str(OUT / "composition-100-selenium.png"))
        d100 = is_disabled(analyze_button(driver))

        result = {
            "analyze_disabled_at_99p5": d995,
            "analyze_enabled_at_100": not d100,
            "block_reason": block_text[:120],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if d995 and not d100 else 2
    except NoSuchElementException as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    finally:
        driver.quit()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())
