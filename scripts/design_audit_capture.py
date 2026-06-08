"""One-off design-review screenshots (Selenium + Chrome CDP)."""
from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoAlertPresentException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from qa_browser_common import (
    CDP_ADDR,
    ELEMS,
    URL,
    find_chrome,
    free_cdp_port,
    fresh_profile,
    start_chrome,
    stop_chrome,
)

OUT = Path.home() / ".gstack/projects/test7/designs/design-audit-20260608/screenshots"


def dismiss_alert(driver) -> None:
    try:
        driver.switch_to.alert.accept()
        time.sleep(0.15)
    except NoAlertPresentException:
        pass


def comp_select(driver):
    for sel in driver.find_elements(By.CSS_SELECTOR, "select"):
        if any(o.text == "원소 추가…" for o in sel.find_elements(By.TAG_NAME, "option")):
            return sel
    raise RuntimeError("composition select not found")


def click_compare_mode(driver, wait: WebDriverWait) -> None:
    btn = driver.find_element(By.XPATH, '//button[@role="tab" and contains(., "비교")]')
    driver.execute_script("arguments[0].click();", btn)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".compare-compose-col--b")))


def col_root(driver, col: str):
    sel = ".compare-compose-col--a" if col == "A" else ".compare-compose-col--b"
    return driver.find_element(By.CSS_SELECTOR, sel)


def ensure_elem(driver, sym: str, col: str = "A") -> None:
    root = col_root(driver, col)
    if root.find_elements(By.XPATH, f".//label[normalize-space()='{sym}']"):
        return
    for btn in root.find_elements(By.CSS_SELECTOR, "button.periodic-cell-btn"):
        if sym in (btn.text or "").split():
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.25)
            return
    sel = root.find_element(By.CSS_SELECTOR, "select")
    Select(sel).select_by_value(sym)
    time.sleep(0.2)


def fill_row(driver, sym: str, val: str, col: str = "A") -> None:
    root = col_root(driver, col)
    row = root.find_element(By.XPATH, f".//label[normalize-space()='{sym}']/..")
    inp = row.find_element(By.CSS_SELECTOR, 'input[type="number"]')
    inp.clear()
    inp.send_keys(val)
    time.sleep(0.15)


def click_analyze(driver) -> None:
    for btn in driver.find_elements(By.CSS_SELECTOR, "button.tactile-hit"):
        if btn.text.strip() == "분석":
            btn.click()
            return
    raise RuntimeError("analyze button not found")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    free_cdp_port()
    fresh_profile()
    proc = start_chrome(URL, find_chrome())
    time.sleep(4)
    opts = Options()
    opts.add_experimental_option("debuggerAddress", CDP_ADDR)
    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, 30)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select")))
        driver.set_window_size(1440, 900)
        click_compare_mode(driver, wait)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".compare-compose-col--b")))
        time.sleep(0.4)
        driver.save_screenshot(str(OUT / "finding-002-after-compare-fold.png"))
        driver.execute_script(
            'document.querySelector(".compare-dual-compose")?.scrollIntoView({block:"start"});'
        )
        time.sleep(0.4)
        driver.save_screenshot(str(OUT / "compare-dual-compose-desktop.png"))

        for sym in ELEMS:
            ensure_elem(driver, sym, "A")
            dismiss_alert(driver)
        fill_row(driver, "Sn", "96.5", "A")
        fill_row(driver, "Ag", "3", "A")
        fill_row(driver, "Bi", "0", "A")
        fill_row(driver, "Cu", "0.5", "A")
        for sym in ELEMS:
            ensure_elem(driver, sym, "B")
            dismiss_alert(driver)
        fill_row(driver, "Sn", "99", "B")
        fill_row(driver, "Ag", "0", "B")
        fill_row(driver, "Bi", "0", "B")
        fill_row(driver, "Cu", "1", "B")
        time.sleep(0.5)
        click_analyze(driver)
        try:
            WebDriverWait(driver, 90).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".compare-hero-panel"))
            )
        except Exception:
            pass
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        driver.save_screenshot(str(OUT / "compare-result-desktop.png"))
        hero = len(driver.find_elements(By.CSS_SELECTOR, ".compare-hero-panel"))
        print(f"saved compare shots; hero_panels={hero}")
    finally:
        driver.quit()
        stop_chrome(proc)


if __name__ == "__main__":
    main()
