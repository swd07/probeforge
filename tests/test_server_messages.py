"""Audit S4: a malformed message gets an error event and the socket stays usable; however the connection ends, the
session ends with it and the local UI run list gets its row."""

import json
import time

from fastapi.testclient import TestClient

from probeforge.server import access, ui_runs
from probeforge.server import app as server


def test_malformed_messages_get_an_error_and_the_socket_stays_open():
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "approval"})  # no id: crashed the handler before
        ev = ws.receive_json()
        assert ev["type"] == "error" and "id must be an integer" in ev["message"]
        ws.send_text("not json")
        assert "not a JSON object" in ws.receive_json()["message"]
        ws.send_json(["a", "list"])
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"action": "tool", "name": "read_panel", "args": "x"})
        assert "args object" in ws.receive_json()["message"]
        ws.send_json({"action": "start_manual", "bench": "ats", "source": "random", "engineer": "x", "token": access.issue()})
        assert ws.receive_json()["type"] == "session"  # the same socket still works


def test_a_closed_connection_cancels_its_session_and_records_the_run():
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_manual", "bench": "ats", "source": "scenario", "scenario": "dev-02",
                      "engineer": "x", "token": access.issue()})
        assert ws.receive_json()["type"] == "session"
    deadline = time.time() + 5
    while time.time() < deadline and not ui_runs.faults_run("ats"):
        time.sleep(0.05)
    rows = ui_runs.faults_run("ats")
    assert [r["ended"] for r in rows] == ["connection closed"]
    assert json.dumps(rows).count("dev-02") == 1
