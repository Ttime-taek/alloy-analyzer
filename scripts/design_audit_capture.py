"""One-off design-review screenshots (Selenium)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

from qa_browser_common import CDP_ADDR, find_chrome, fresh_profile, free_cdp_port, start_chrome, stop_chrome  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else _ROOT / ".gstack" / "design-audit-capture"
URL = "http://127.0.0.1:8000/"
COMP = {"Sn": "96.5", "Ag": "3.0", "Cu": "0.5"}


def comp_select(driver):
    for sel in driver.find_elements(By.CSS_SELECTOR, "select"):
        if any(o.text == "원소 추가…" for o in sel.find_elements(By.TAG_NAME, "option")):
            return sel
    raise RuntimeError("composition select not found")


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
    time.sleep(0.15)


def analyze_btn(driver):
    for btn in driver.find_elements(By.CSS_SELECTOR, "button.tactile-hit"):
        if btn.text.strip() == "분석":
            return btn
    raise RuntimeError("analyze button not found")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    free_cdp_port()
    fresh_profile()
    proc = start_chrome(URL, find_chrome())
    time.sleep(4)
    opts = Options()
    opts.add_experimental_option("debuggerAddress", CDP_ADDR)
    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, 45)
    try:
        driver.get(URL)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select")))
        time.sleep(0.8)
        driver.save_screenshot(str(OUT / "first-impression.png"))

        for sym in COMP:
            ensure_elem(driver, sym)
        for sym, val in COMP.items():
            fill_row(driver, sym, val)
        time.sleep(0.5)
        driver.save_screenshot(str(OUT / "composition-filled.png"))

        analyze_btn(driver).click()
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".summary-card")) >= 3)
        time.sleep(1.2)
        driver.save_screenshot(str(OUT / "results-desktop.png"))

        driver.set_window_size(390, 844)
        time.sleep(0.8)
        driver.save_screenshot(str(OUT / "results-mobile.png"))
        print(f"OK: saved to {OUT}")
        return 0
    finally:
        driver.quit()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())
