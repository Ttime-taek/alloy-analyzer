"""Shared Chrome CDP helpers for QA scripts (Windows-friendly)."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

URL = "http://127.0.0.1:8000/"
PROFILE = Path(__file__).resolve().parents[1] / ".gstack" / "chrome-qa-profile"
CDP_ADDR = "127.0.0.1:9222"
ELEMS = ["Sn", "Ag", "Bi", "Cu"]


def find_chrome() -> Path:
    for p in [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]:
        if p.is_file():
            return p
    raise FileNotFoundError("Chrome/Edge not found")


def free_cdp_port() -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue | "
            "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }",
        ],
        capture_output=True,
        timeout=15,
    )
    time.sleep(1)


def fresh_profile() -> None:
    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    PROFILE.mkdir(parents=True, exist_ok=True)


def start_chrome(url: str = URL, exe: Path | None = None) -> subprocess.Popen:
    chrome = exe or find_chrome()
    return subprocess.Popen(
        [
            str(chrome),
            "--remote-debugging-port=9222",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_chrome(proc: subprocess.Popen | None) -> None:
    if proc is not None:
        proc.terminate()
    free_cdp_port()


def pick_cdp_page(browser, url_fragment: str = "127.0.0.1:8000"):
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if url_fragment in (pg.url or ""):
                return pg
    if browser.contexts and browser.contexts[0].pages:
        return browser.contexts[0].pages[0]
    return browser.contexts[0].new_page()


def reset_ui_page(page) -> None:
    btn = page.get_by_role("button", name="초기화")
    if btn.count():
        btn.first.click()
        page.wait_for_timeout(600)


def ensure_elem_page(page, sym: str) -> None:
    if page.locator(f"//label[normalize-space()='{sym}']").count() > 0:
        return
    sel = page.locator("select").filter(has=page.locator("option", has_text="원소 추가…")).first
    sel.select_option(sym)
    page.wait_for_timeout(250)


def fill_wt_page(page, sym: str, val: str) -> None:
    row = page.locator(f"//label[normalize-space()='{sym}']/..")
    row.locator('input[type="number"]').first.fill(val)
    page.wait_for_timeout(200)


def run_composition_gate_check(page, out_dir: Path, prefix: str = "") -> dict:
    """99.5% disabled, 100% enabled. Returns result dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    p = prefix + "-" if prefix else ""

    reset_ui_page(page)
    for sym in ELEMS:
        ensure_elem_page(page, sym)

    fill_wt_page(page, "Sn", "96.2")
    fill_wt_page(page, "Ag", "0.3")
    fill_wt_page(page, "Bi", "3")
    fill_wt_page(page, "Cu", "0")
    page.wait_for_timeout(600)
    page.screenshot(path=str(out_dir / f"{p}composition-99p5.png"), full_page=True)

    analyze = page.get_by_role("button", name="분석")
    d995 = analyze.is_disabled()

    fill_wt_page(page, "Cu", "0.5")
    page.wait_for_timeout(600)
    page.screenshot(path=str(out_dir / f"{p}composition-100.png"), full_page=True)
    d100 = analyze.is_disabled()

    block = page.locator("[role='status']").first.inner_text(timeout=3000) if page.locator("[role='status']").count() else ""

    return {
        "analyze_disabled_at_99p5": d995,
        "analyze_enabled_at_100": not d100,
        "block_reason": block[:120],
    }
