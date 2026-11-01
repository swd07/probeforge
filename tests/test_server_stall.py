"""S1 from the audit (2026-11-01), reproduced against a real uvicorn process: one client with an approval pending and a
stream of queued tool messages must not stall another visitor's tool call."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import websockets

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    port = free_port()
    env = {**os.environ, "PROBEFORGE_UI_RUNS": str(tmp_path / "ui_runs.jsonl"), "PROBEFORGE_OFFLINE": "1",
           "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.Popen([sys.executable, "-m", "probeforge.server", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.3)
    yield port
    proc.terminate()
    proc.wait(timeout=20)


async def start_engineer(port: int):
    import urllib.request

    try:
        token = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/session-token").read())["token"]
    except OSError:  # before the token endpoint existed
        token = None
    ws = await websockets.connect(f"ws://127.0.0.1:{port}/ws", origin=f"http://127.0.0.1:{port}")
    await ws.send(json.dumps({"action": "start_manual", "bench": "ats", "source": "scenario", "scenario": "dev-01",
                              "engineer": "test", "token": token}))
    while json.loads(await ws.recv())["type"] != "session":
        pass
    return ws


async def until(ws, kind: str, timeout: float) -> dict:
    async with asyncio.timeout(timeout):
        while True:
            ev = json.loads(await ws.recv())
            if ev["type"] == kind:
                return ev


def test_a_pending_approval_and_queued_tool_calls_do_not_stall_another_visitor(server):
    async def scenario():
        a = await start_engineer(server)
        await a.send(json.dumps({"action": "tool", "name": "isolate_sources", "args": {"reason": "ohmmeter"}}))
        await until(a, "approval_request", 20)  # A's worker now waits for the approval
        for _ in range(30):  # and A floods its session with more tool calls
            await a.send(json.dumps({"action": "tool", "name": "read_panel", "args": {}}))
        b = await start_engineer(server)
        await b.send(json.dumps({"action": "tool", "name": "read_panel", "args": {}}))
        ev = await until(b, "tool", 5)  # B is served at once
        assert ev["tool"] == "read_panel" and ev["executed"]
        # A's extra calls were refused while its step was pending (one may wait in the queue), not piled up
        refused = 0
        async with asyncio.timeout(5):
            while refused < 29:
                ev = json.loads(await a.recv())
                if ev["type"] == "error" and "still pending" in ev["message"]:
                    refused += 1
        await a.close()
        await b.close()

    asyncio.run(scenario())


def test_connections_over_the_per_ip_cap_are_refused(monkeypatch):
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from probeforge.server import app as server

    monkeypatch.setattr(server.settings, "MAX_PER_IP", 1)
    client = TestClient(server.app)
    with client.websocket_connect("/ws"):
        with pytest.raises(WebSocketDisconnect) as refused:
            with client.websocket_connect("/ws"):
                pass
        assert refused.value.code == 1013  # try again later


def test_a_run_is_refused_when_every_run_worker_is_busy(monkeypatch):
    from fastapi.testclient import TestClient

    from probeforge.server import app as server

    monkeypatch.setitem(server._jobs, "running", server.settings.JOB_WORKERS)
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "start", "bench": "ats", "source": "random", "effort": "low"})
        ev = ws.receive_json()
        assert ev["type"] == "error" and "busy" in ev["message"]
