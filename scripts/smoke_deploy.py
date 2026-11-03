"""Smoke test of a deployed ProbeForge (docs/DEPLOY.md), from outside, with no API key and no paid call.

    uv run python scripts/smoke_deploy.py https://demo.example.org [--headers] [--browser]

Waits first until the app has finished its start-up warm-up (/api/ready, D62); while it warms, the proxy serves the
starting page, which is checked when seen. Checks: the health endpoint and public mode; the page and its script; the ATS meta (the 12 dev cases, the saved
Hybrid read listed, the never-tier count from the committed runs); the drawing SVG; the troubleshooting sheet; that
repo files are not served; the WebSocket through the proxy: a foreign Origin refused, a start without or with a forged
token refused, a free Engineer session opened with a valid token and a reading taken; whether paid runs are open.
--headers: the security headers are set. --browser: the page loads in Chromium with no console error (a blocked
script, style or WebSocket shows there) and an Engineer session starts. Exit status 1 on any failure.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

import websockets

DEFAULT_READ = "run_20261031_003748"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def get(base: str, path: str) -> tuple[int, dict, bytes]:
    try:
        with urllib.request.urlopen(base + path, timeout=60) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def wait_ready(base: str, timeout_s: float) -> None:
    """Until /api/ready says ready. Behind Caddy every request gets the starting page (503) while the app warms up."""
    t0, seen_starting = time.monotonic(), False
    while True:
        code, _, body = get(base, "/api/ready")
        if code == 200 and json.loads(body).get("ready") is True:
            break
        if code == 503 and not seen_starting:
            code_page, _, page = get(base, "/")
            if code_page == 503 and b"ProbeForge is starting" in page:
                seen_starting = True
                check("starting page while the app warms up", True)
        if time.monotonic() - t0 > timeout_s:
            check("ready (start-up warm-up done)", False, f"not ready after {timeout_s:.0f} s")
            return
        time.sleep(3)
    check("ready (start-up warm-up done)", True, f"after {time.monotonic() - t0:.0f} s of waiting")


def http_checks(base: str, headers: bool) -> None:
    code, _, body = get(base, "/api/health")
    health = json.loads(body) if code == 200 else {}
    check("health", code == 200 and health.get("ok") is True, str(health))
    check("public mode", health.get("public") is True)
    check("warm-up done at start (public mode)", health.get("warm", {}).get("warm_at_start") is True and health.get("ready") is True)
    print(f"     paid runs open: {health.get('paid_runs_open')}")

    code, h, body = get(base, "/")
    page = body.decode("utf-8", "replace")
    check("page", code == 200 and '<div id="root">' in page)
    script = re.search(r'src="(/assets/[^"]+\.js)"', page)
    check("page script", bool(script) and get(base, script.group(1))[0] == 200 if script else False)
    if headers:
        csp = h.get("content-security-policy", "")
        check("security headers", "default-src 'self'" in csp and h.get("x-content-type-options") == "nosniff"
              and h.get("x-frame-options") == "DENY", csp[:80])

    code, _, body = get(base, "/api/meta")
    check("motor starter hidden (public)", code == 200 and json.loads(body).get("public") is True)
    code, _, body = get(base, "/api/ats/meta")
    meta = json.loads(body) if code == 200 else {}
    check("ATS dev cases", len(meta.get("scenarios", [])) == 12, f"{len(meta.get('scenarios', []))} cases")
    reads = [t["id"] for t in meta.get("transcriptions", [])]
    check("saved Hybrid read listed", DEFAULT_READ in reads, ", ".join(reads))
    check("live re-read off", meta.get("live_read", {}).get("available") is False)
    never = meta.get("never_attempts") or {}
    check("never-tier count (committed runs in the image)", never.get("agent", {}).get("runs", 0) > 0, json.dumps(never))

    code, h, body = get(base, "/api/ats/schematic")
    check("drawing SVG", code == 200 and "svg" in h.get("content-type", "") and body.lstrip()[:5] in (b"<svg ", b"<?xml"))
    code, _, body = get(base, "/api/ats/troubleshooting")
    sheet = json.loads(body) if code == 200 else {}
    check("troubleshooting sheet", code == 200 and bool(sheet), f"{len(body)} bytes")

    for path in ("/.env", "/docs/NEXT_STEPS.md", "/runs/public_spend.json", "/src/probeforge/server/app.py",
                 "/scenarios/ats/a1_coil_open.yaml", "/%2e%2e/.env"):
        code = get(base, path)[0]
        check(f"not served: {path}", code == 404, str(code))


async def ws_checks(base: str) -> None:
    u = urlparse(base)
    ws_url = ("wss" if u.scheme == "https" else "ws") + f"://{u.netloc}/ws"
    origin = f"{u.scheme}://{u.netloc}"
    try:
        async with websockets.connect(ws_url, origin="https://evil.example"):
            check("foreign Origin refused", False, "accepted")
    except websockets.InvalidStatus as e:
        check("foreign Origin refused", e.response.status_code == 403, str(e.response.status_code))
    async with websockets.connect(ws_url, origin=origin) as ws:
        start = {"action": "start_manual", "bench": "ats", "source": "scenario", "scenario": "dev-07", "engineer": "smoke"}
        for name, tok in (("start without a token refused", None), ("start with a forged token refused", "1.abc")):
            await ws.send(json.dumps({**start, **({"token": tok} if tok else {})}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), 20))
            check(name, msg.get("type") == "error" and "token" in msg.get("message", ""), msg.get("message", ""))
        token = json.loads(get(base, "/api/session-token")[2])["token"]
        await ws.send(json.dumps({**start, "token": token}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), 60))
        check("Engineer session opens through the proxy", msg.get("type") == "session", msg.get("type", ""))
        await ws.send(json.dumps({"action": "tool", "name": "read_panel", "args": {}}))
        seen = None
        for _ in range(10):
            m = json.loads(await asyncio.wait_for(ws.recv(), 30))
            if m.get("type") == "tool":
                seen = m
                break
        check("a reading through the WebSocket", bool(seen) and seen.get("executed") is True)
        await ws.send(json.dumps({"action": "stop"}))


def browser_check(base: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("SMOKE_BROWSER_CHANNEL") or None)  # e.g. msedge locally
        page = b.new_page(viewport={"width": 1440, "height": 900})
        console: list[str] = []
        page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console.append(str(e)))
        page.goto(base + "/")
        # a locator, not wait_for_function: the page's CSP (rightly) refuses Playwright's string eval
        page.locator('select[aria-label="Fault"] option').nth(5).wait_for(state="attached", timeout=60000)
        check("browser: ATS bench shown, no Motor starter button",
              page.locator(".segmented button", has_text="Motor starter").count() == 0)
        page.locator(".segmented button", has_text="Engineer").click()
        page.select_option('select[aria-label="Fault"]', "dev-07")
        page.locator(".btn.start").click()
        page.wait_for_selector(".suggest-btn", timeout=60000)
        check("browser: Engineer session starts", page.locator(".topbar .status").inner_text() == "Your turn")
        page.click("button.stop")
        page.wait_for_timeout(1000)
        check("browser: no console errors (CSP, WebSocket, script)", not console, "; ".join(console)[:300])
        b.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--headers", action="store_true", help="the security headers are expected (behind Caddy)")
    ap.add_argument("--browser", action="store_true", help="load the page in Chromium (playwright)")
    ap.add_argument("--ready-timeout", type=float, default=900, help="seconds to wait for the start-up warm-up (up to about 10 min on a small VPS)")
    a = ap.parse_args()
    base = a.url.rstrip("/")
    wait_ready(base, a.ready_timeout)
    http_checks(base, a.headers)
    asyncio.run(ws_checks(base))
    if a.browser:
        browser_check(base)
    print(f"\n{len(failures)} failed" + (": " + ", ".join(failures) if failures else ""))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
