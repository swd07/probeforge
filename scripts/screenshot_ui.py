"""Drive the web UI through a full live run and save screenshots.

Needs the backend running with the built frontend:
  (cd web && npm run build) && uv run python -m probeforge.server
Then:
  uv run python scripts/screenshot_ui.py --choice s08 --name s08
Uses the installed Microsoft Edge through Playwright (no browser download).
Approval requests are answered with --answer approve|deny (default approve).
"""

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--choice", default="random", help="random or a scenario id like s08")
    ap.add_argument("--name", default="run")
    ap.add_argument("--answer", choices=["approve", "deny"], default="approve")
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--fault", default=None, help="test hook: inject this fault, e.g. 'QF1:5-6 open'")
    ap.add_argument("--width", type=int, default=1680)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--mode", choices=["agent", "hybrid"], default="agent")
    ap.add_argument("--schematic", choices=["saved", "live"], default="saved", help="hybrid: which schematic read")
    args = ap.parse_args()
    out = ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": args.width, "height": args.height}, device_scale_factor=1)
        page.goto(args.url + (f"/?fault={args.fault}" if args.fault else ""))
        page.wait_for_selector(".schematic svg")
        page.screenshot(path=out / f"{args.name}_0_ready.png")
        if args.mode == "hybrid":
            page.click(".segmented button:has-text(\"Hybrid\")")
            page.select_option("select[aria-label=\"Schematic read\"]", args.schematic)
        page.select_option("select[aria-label=Fault]", args.choice)
        page.click("button.start")

        shots = {"probing": 3, "midrun": 9}
        taken: set[str] = set()
        approvals = 0
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            n_tools = page.eval_on_selector_all(".feed .item.tool", "els => els.length")
            n_probe = page.eval_on_selector_all(".schematic .reading", "els => els.length")
            for name, at in shots.items():
                if name not in taken and n_tools >= at and n_probe > 0:
                    page.screenshot(path=out / f"{args.name}_{len(taken) + 1}_{name}.png")
                    taken.add(name)
            for name, sel in (("conflict", ".item.conflict"), ("correction", ".item.correction")):
                if name not in taken and page.query_selector(sel):
                    time.sleep(0.4)
                    page.screenshot(path=out / f"{args.name}_{len(taken) + 1}_{name}.png")
                    taken.add(name)
            if page.query_selector(".flags-modal"):
                page.screenshot(path=out / f"{args.name}_flags.png")
                page.click(".flags-modal button.approve")
            if page.query_selector(".approval-modal"):
                approvals += 1
                page.screenshot(path=out / f"{args.name}_approval_{approvals}.png")
                page.click(f"button.{args.answer}")
            if page.query_selector(".result-card") or page.query_selector(".error-banner"):
                break
            time.sleep(0.5)
        time.sleep(1)
        page.screenshot(path=out / f"{args.name}_8_result.png")
        if page.query_selector(".result-card button.ghost"):
            page.click(".result-card button.ghost")
            time.sleep(0.5)
            page.screenshot(path=out / f"{args.name}_9_true_wiring.png")
        browser.close()
    print(f"screenshots in {out} (approvals answered: {approvals})")


if __name__ == "__main__":
    main()
