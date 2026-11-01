"""Audit S5: the engineer name is slugged before it reaches a file path, and in public mode a visitor's Engineer-mode
trace is kept apart: it is never the "recorded engineer trace" of another visitor's Compare."""

import pytest
from fastapi.testclient import TestClient

from probeforge.server import access, ats_common, settings
from probeforge.server import app as server
from probeforge.server.ats_views import engineer_trace
from probeforge.server.names import slug

DIAGNOSIS = {"outcome": "insufficient_information", "confidence": 0.1,
             "evidence": [{"step": 0, "type": "functional_test", "observation": "panel at the start"}]}


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(ats_common, "ENGINEER_DIR", tmp_path / "engineer_traces")
    monkeypatch.setattr(ats_common, "VISITOR_DIR", tmp_path / "visitor_traces")
    monkeypatch.setattr(ats_common, "warm_signatures", lambda: None)
    monkeypatch.setattr(ats_common, "catalog_signatures", lambda: {})
    return tmp_path


def engineer_run(name: str) -> dict:
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_manual", "bench": "ats", "source": "scenario", "scenario": "dev-01",
                      "engineer": name, "token": access.issue()})
        while ws.receive_json()["type"] != "session":
            pass
        ws.send_json({"action": "tool", "name": "submit_diagnosis", "args": DIAGNOSIS})
        while True:
            ev = ws.receive_json()
            if ev["type"] in ("saved", "error"):
                return ev


def test_a_hostile_engineer_name_stays_inside_the_traces_folder(dirs):
    ev = engineer_run("..\\..\\pwned/../x:y?" + "z" * 10_000)
    assert ev["type"] == "saved", ev
    files = [p for p in dirs.rglob("*.json")]
    assert len(files) == 1 and files[0].parent == dirs / "engineer_traces" and len(files[0].name) < 200
    assert slug("../a b") == "a-b" and slug("") == "x"


def test_in_public_mode_visitor_traces_never_reach_compare(dirs, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC", True)
    assert engineer_run("Visitor")["type"] == "saved"
    assert list((dirs / "visitor_traces").glob("*.json")) and not (dirs / "engineer_traces").exists()
    from probeforge.faults.model import Fault

    assert engineer_trace([Fault("TS", "open", "A-B")]) is None  # a1's fault: no reference trace for Compare
