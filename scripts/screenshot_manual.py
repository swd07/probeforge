"""Play a short manual (engineer) session in the UI and save screenshots, then open the comparison.

Needs the backend running with the built frontend (see screenshot_ui.py). The compare step runs
the real agent once (about $0.05). Scenario s04: forward contactor KM1 coil open.
"""

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1680, "height": 1000})
        page.goto("http://127.0.0.1:8000")
        page.wait_for_selector(".schematic svg")

        page.click(".topbar .segmented button:has-text('Engineer')")
        page.select_option("select[aria-label=Fault]", "s04")
        page.fill("input[aria-label='Engineer name']", "Demo engineer")
        page.click("button.start")
        page.wait_for_selector(".manual-card")

        def tools() -> int:
            return page.eval_on_selector_all(".feed .item.tool", "els => els.length")

        def act(fn):
            before = tools()
            fn()
            page.wait_for_function(f"document.querySelectorAll('.feed .item.tool').length > {before}", timeout=20000)
            time.sleep(0.3)

        def pick(point: str):
            page.click(f".schematic circle[data-terminal='{point}']", force=True)

        act(lambda: page.click("[aria-label='Start Fwd']"))
        act(lambda: page.click("[aria-label='Start Rev']"))
        act(lambda: page.click("[aria-label='Stop']"))

        page.click(".meter-controls .segmented button:has-text('Ω')")
        pick("KM1:A1")
        pick("KM1:A2")
        page.screenshot(path=OUT / "manual_1_probes_placed.png")
        act(lambda: page.click("button:has-text('Measure')"))  # blocked: power is on
        page.screenshot(path=OUT / "manual_2_blocked.png")

        act(lambda: page.click("[aria-label='Main breaker']"))
        pick("KM1:A1")
        pick("KM1:A2")
        act(lambda: page.click("button:has-text('Measure')"))
        pick("KM2:A1")
        pick("KM2:A2")
        act(lambda: page.click("button:has-text('Measure')"))
        time.sleep(0.5)
        page.screenshot(path=OUT / "manual_3_measured.png")

        page.click("button:has-text('Diagnose')")
        selects = page.locator(".diag-modal select")
        selects.nth(0).select_option("KM1")
        selects.nth(1).select_option("A1-A2")
        selects.nth(2).select_option("open")
        for text in ("Press SB2", "Resistance KM1:A1"):
            page.locator(".evidence li", has_text=text).first.locator("input").check()
        page.screenshot(path=OUT / "manual_4_diagnosis_form.png")
        page.click(".diag-modal button:has-text('Submit')")
        page.wait_for_selector(".result-card")
        time.sleep(0.5)
        page.screenshot(path=OUT / "manual_5_result.png")

        page.click("button:has-text('Compare with agent and baseline')")
        page.wait_for_function("!document.querySelector('.cmp-col.pending')", timeout=300000)
        time.sleep(0.5)
        page.screenshot(path=OUT / "manual_6_compare.png")
        browser.close()
    print(f"screenshots in {OUT}")


if __name__ == "__main__":
    main()
