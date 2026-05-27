"""Minimal selenium smoke: load app and count buttons."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

URL = "http://127.0.0.1:8000/?smoke=1"
OUT = Path(__file__).resolve().parents[1] / ".gstack" / "slide-verify-20260526"
OUT.mkdir(parents=True, exist_ok=True)

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--window-size=1400,900")
driver = webdriver.Chrome(options=opts)
try:
    driver.get(URL)
    time.sleep(3)
    root = driver.find_element(By.ID, "root").get_attribute("innerHTML") or ""
    logs = driver.get_log("browser")
    print("title", driver.title)
    print("root_len", len(root))
    print("console", [e.get("message", "")[:200] for e in logs[:8]])
    driver.save_screenshot(str(OUT / "smoke.png"))
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "button")))
    btns = [b.text.strip() for b in driver.find_elements(By.TAG_NAME, "button") if b.text.strip()]
    print("buttons", len(btns), btns[:8])
except Exception as exc:
    print("FAIL", exc)
    try:
        print("page", driver.page_source[:800])
    except Exception:
        pass
    raise
finally:
    driver.quit()
