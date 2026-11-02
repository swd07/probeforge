"""Deployment options (docs/DEPLOY.md): proxy headers only from the configured proxy, so the per-address limit sees the
visitor behind Caddy; the Origin allow-list and the allowed hosts from the env file; the health endpoint."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import websockets
from fastapi.testclient import TestClient

from probeforge.server import access
from probeforge.server.__main__ import uvicorn_options

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_server(tmp_path, **env):
    port = free_port()
    e = {**os.environ, "PROBEFORGE_UI_RUNS": str(tmp_path / "ui_runs.jsonl"), "PROBEFORGE_OFFLINE": "1",
         "PYTHONPATH": str(ROOT / "src"), **env}
    proc = subprocess.Popen([sys.executable, "-m", "probeforge.server", "--port", str(port)], cwd=ROOT, env=e,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.3)
    return proc, port


def test_proxy_headers_only_when_a_proxy_is_configured():
    assert uvicorn_options({})["proxy_headers"] is False
    o = uvicorn_options({"PROBEFORGE_FORWARDED_ALLOW_IPS": "172.30.0.10"})
    assert o["proxy_headers"] is True and o["forwarded_allow_ips"] == "172.30.0.10"


def test_the_configured_origins_are_the_only_ones():
    demo = {"https://demo.example.org"}
    assert access.origin_allowed("https://demo.example.org", "demo.example.org", demo)
    assert not access.origin_allowed("https://evil.example", "demo.example.org", demo)
    assert not access.origin_allowed("http://localhost:5173", "demo.example.org", demo)  # no dev origin when deployed
    assert access.origin_allowed("http://127.0.0.1:8000", "127.0.0.1:8000", set())  # local: same host


def test_health():
    from probeforge.server import app as server
    r = TestClient(server.app).get("/api/health").json()
    assert r["ok"] is True and isinstance(r["paid_runs_open"], bool) and "public" in r


async def first_message(port, xff):
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws", additional_headers={"X-Forwarded-For": xff}) as a:
        await a.send(json.dumps({"action": "stop"}))
        held = json.loads(await a.recv())
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws", additional_headers={"X-Forwarded-For": xff}) as b:
            same = json.loads(await b.recv())
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws",
                                      additional_headers={"X-Forwarded-For": "203.0.113.99"}) as c:
            try:  # a refused connection says why at once; an accepted one stays silent
                other = json.loads(await asyncio.wait_for(c.recv(), 2))
            except asyncio.TimeoutError:
                other = {"message": "accepted"}
    return held, same, other


def test_behind_the_proxy_the_limit_counts_the_visitor(tmp_path):
    proc, port = run_server(tmp_path, PROBEFORGE_FORWARDED_ALLOW_IPS="127.0.0.1", PROBEFORGE_MAX_PER_IP="1")
    try:
        held, same, other = asyncio.run(first_message(port, "203.0.113.5"))
    finally:
        proc.terminate()
        proc.wait(timeout=20)
    assert held["message"] == "No session is running."
    assert "already has 1 open" in same["message"]  # the same visitor again: refused
    assert other["message"] == "accepted"  # another visitor through the same proxy


def test_a_forwarded_header_from_an_untrusted_client_is_ignored(tmp_path):
    proc, port = run_server(tmp_path, PROBEFORGE_FORWARDED_ALLOW_IPS="10.9.9.9", PROBEFORGE_MAX_PER_IP="1")
    try:
        held, same, other = asyncio.run(first_message(port, "203.0.113.5"))
    finally:
        proc.terminate()
        proc.wait(timeout=20)
    assert "already has 1 open" in other["message"]  # a made-up address does not get a second connection


def test_allowed_hosts(tmp_path):
    proc, port = run_server(tmp_path, PROBEFORGE_ALLOWED_HOSTS="demo.example.org")
    try:
        def status(host):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health", headers={"Host": host})
            try:
                return urllib.request.urlopen(req, timeout=10).status
            except urllib.error.HTTPError as e:
                return e.code
        assert status("demo.example.org") == 200
        assert status("evil.example") == 400
        assert status(f"127.0.0.1:{port}") == 200  # the container's own health check
    finally:
        proc.terminate()
        proc.wait(timeout=20)
