"""The public demo shows the transfer switch bench only: the meta says so and the server refuses a motor starter
start; locally the motor starter stays available."""

from fastapi.testclient import TestClient

from probeforge.server import access, settings
from probeforge.server import app as server


def test_public_mode_refuses_the_motor_starter(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC", True)
    client = TestClient(server.app)
    assert client.get("/api/meta").json()["public"] is True
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_manual", "source": "random", "engineer": "x", "token": access.issue()})
        ev = ws.receive_json()
        assert ev["type"] == "error" and ev["message"] == server.PUBLIC_BENCH_MESSAGE
        ws.send_json({"action": "start_manual", "bench": "ats", "source": "random", "engineer": "x", "token": access.issue()})
        assert ws.receive_json()["type"] == "session"  # the ATS bench works


def test_locally_the_motor_starter_runs(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC", False)
    client = TestClient(server.app)
    assert client.get("/api/meta").json()["public"] is False
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_manual", "source": "random", "engineer": "x", "token": access.issue()})
        assert ws.receive_json()["type"] == "session"
