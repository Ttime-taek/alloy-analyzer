"""UI QA via Selenium + Chrome remote debugging (no Playwright driver)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

OUT = Path(__file__).resolve().parents[1] / ".gstack" / "qa-reports" / "screenshots"
URL = "http://127.0.0.1:8000/"
PROFILE = Path(__file__).resolve().parents[1] / ".gstack" / "chrome-qa-profile"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
ELEMS = ["Sn", "Ag", "Bi", "Cu"]


def start_chrome() -> subprocess.Popen:
    PROFILE.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            str(CHROME),
            "--remote-debugging-port=9222",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            URL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def comp_select(driver):
    """First 'add element' dropdown under composition A."""
    for sel in driver.find_elements(By.CSS_SELECTOR, "select"):
        if any(o.text == "원소 추가…" for o in sel.find_elements(By.TAG_NAME, "option")):
            return sel
    raise RuntimeError("composition select not found")


def add_elem(driver, sym: str) -> None:
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
    pe = btn.value_of_css_property("pointer-events")
    return pe == "none"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    proc = start_chrome()
    time.sleep(4)

    opts = Options()
    opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, 30)

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select")))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.save_screenshot(str(OUT / "home-selenium.png"))

        for sym in ELEMS:
            add_elem(driver, sym)

        fill_row(driver, "Sn", "96.2")
        fill_row(driver, "Ag", "0.3")
        fill_row(driver, "Bi", "3")
        fill_row(driver, "Cu", "0")
        time.sleep(0.6)
        driver.save_screenshot(str(OUT / "composition-99p5-selenium.png"))

        analyze = analyze_button(driver)
        d995 = is_disabled(analyze)
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
    finally:
        driver.quit()
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
