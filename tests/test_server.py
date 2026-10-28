"""Web backend: one live session over the WebSocket, with a scripted fake model."""

import json

from fastapi.testclient import TestClient

import pytest

from probeforge.agent import loop
from probeforge.eval.spend import SpendLedger
from probeforge.faults import Fault
from probeforge.server import app as server
from tests.test_agent_loop import FakeClient, FakeMessage

@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Never touch the real spend ledger or the engineer reference folder from tests."""
    ledger = SpendLedger(tmp_path / "spend.json")
    monkeypatch.setattr(server, "ledger", lambda: ledger)
    monkeypatch.setattr(server, "ENGINEER_DIR", tmp_path / "engineer_traces")
    monkeypatch.setattr(server, "COMPARE_DIR", tmp_path / "compare")
    return tmp_path


HYP = {"hypotheses": [{"component": "FU2", "part": "5-6", "failure_mode": "open", "probability": 0.8, "reason": "W zero"}]}


def script():
    return FakeClient([
        FakeMessage(calls=[("press_button", {"button": "Start Fwd"})]),                         # step 1: hums
        FakeMessage(calls=[("wait", {"seconds": 10})]),                                          # step 2: KK1 trips
        FakeMessage(calls=[("measure_voltage", {"point_a": "L3F", "point_b": "N"})]),           # step 3
        FakeMessage(calls=[("update_hypotheses", HYP), ("set_power", {"on": False})]),          # steps 4, 5
        FakeMessage(calls=[("measure_voltage", {"point_a": "1", "point_b": "N"})]),             # step 6: blocked (power off)
        FakeMessage(calls=[("set_power", {"on": True, "reason": "check the supply side again"})]),  # step 7: approval
        FakeMessage(calls=[("update_hypotheses", HYP),
                           ("submit_diagnosis", {"outcome": "diagnosed", "component": "FU2", "part": "5-6",
                                                 "failure_mode": "open", "confidence": 0.9,
                                                 "evidence": [{"step": 3, "type": "instrument_reading", "observation": "L3F 0 V"}]})]),
    ])


def test_live_session_with_approval(monkeypatch):
    monkeypatch.setattr(server, "client", script)
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    http = TestClient(server.app)

    meta = http.get("/api/meta").json()
    assert meta["neutral"] == "N" and len(meta["scenarios"]) == 8
    assert all(set(s) == {"id", "symptom"} for s in meta["scenarios"])  # titles would name the fault
    assert http.get("/api/schematic").text.startswith("<svg")

    events = []
    with http.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start", "source": "scenario", "scenario": "s08", "effort": "low"})
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] == "approval_request":
                assert ev["tool"] == "set_power" and ev["agent_reason"] == "check the supply side again"
                ws.send_json({"action": "approval", "id": ev["id"], "approve": True})
            if ev["type"] in ("done", "error"):
                break

    types = [e["type"] for e in events]
    assert types[0] == "session" and types[-1] == "done"
    assert "approval_answer" in types and "hypotheses" in types

    tools = [e for e in events if e["type"] == "tool"]
    blocked = [e for e in tools if e["verdict"] == "block"]
    assert len(blocked) == 1 and "power on" in blocked[0]["policy_reason"]
    probe = next(e for e in tools if e["tool"] == "measure_voltage" and e["executed"])["probes"][0]
    assert probe["net_a"] == "L3F" and probe["value"] == 0.0 and probe["term_a"] == "FU2:6"
    assert all("panel" in e for e in tools)

    before_done = json.dumps(events[:-1])
    assert "FU2:5-6 open" not in before_done and "Phase loss" not in before_done
    assert "truth_live_nets" not in before_done

    done = events[-1]
    assert done["fault"] == "FU2:5-6 open" and done["verdict"] == "correct"
    assert done["approvals"] == 1 and done["approvals_denied"] == 0 and done["policy_blocked"] == 1
    assert "L1" in done["truth_live_nets"]


def test_random_fault_is_hidden_until_done(monkeypatch):
    monkeypatch.setattr(server, "client", lambda: FakeClient([
        FakeMessage(calls=[("submit_diagnosis", {"outcome": "insufficient_information", "confidence": 0.1, "evidence": []})]),
    ]))
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "start", "source": "random", "effort": "low"})
        events = []
        while not events or events[-1]["type"] not in ("done", "error"):
            events.append(ws.receive_json())
    assert events[0]["source"] == "random fault (any of 91)" == events[-1]["source"]
    fault = events[-1]["fault"]
    assert fault and fault not in json.dumps(events[:-1])


def test_clean_pool_fault_comes_from_holdout_clean(monkeypatch):
    import yaml

    from probeforge.faults.catalog import SCENARIOS_DIR

    monkeypatch.setattr(server, "client", lambda: FakeClient([
        FakeMessage(calls=[("submit_diagnosis", {"outcome": "insufficient_information", "confidence": 0.1, "evidence": []})]),
    ]))
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    clean = yaml.safe_load((SCENARIOS_DIR / "holdout_clean.yaml").read_text(encoding="utf-8"))["cases"]
    pool = {str(Fault.from_dict(c)) for c in clean}
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "start", "source": "clean", "effort": "low"})
        events = []
        while not events or events[-1]["type"] not in ("done", "error"):
            events.append(ws.receive_json())
    done = events[-1]
    assert done["source"] == f"clean test fault (holdout_clean.yaml, {len(pool)})"
    assert done["fault"] in pool


def test_hybrid_session_saved_transcription(monkeypatch):
    from tests.test_hybrid import FakeClient as HybridFake, true_data

    monkeypatch.setattr(server, "client", lambda: HybridFake(true_data()))
    monkeypatch.setattr(server, "render_png", lambda n: b"png")
    http = TestClient(server.app)
    events = []
    with http.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_hybrid", "source": "random", "schematic": "saved",
                      "fault": "KM4:3-4 stuck_open"})
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] in ("done", "error"):
                break
    kinds = [e["type"] for e in events]
    assert kinds[0] == "session" and "transcription" in kinds and "conflict" in kinds and "correction" in kinds
    assert "hypotheses" in kinds and kinds[-1] == "done"
    done = events[-1]
    assert done["mode"] == "hybrid" and done["verdict"] == "correct" and done["transcription_wrong_nets"] == 6
    assert done["corrections"] and done["explanation"]
    # nothing before "done" names the injected fault as such
    assert all("fault" not in e for e in events[:-1])


def test_hybrid_flags_need_confirmation(monkeypatch):
    from tests.test_hybrid import FakeClient as HybridFake, true_data

    flagged = {**true_data(), "uncertain": [{"terminals": ["KM2:1", "KM2:5"], "reason": "wires cross"}]}
    monkeypatch.setattr(server, "client", lambda: HybridFake(true_data()))
    monkeypatch.setattr(server, "render_png", lambda n: b"png")
    monkeypatch.setattr(server.HybridSession, "read", lambda self, usage: (flagged, [flagged["uncertain"][0]], "test", b"png"))
    http = TestClient(server.app)
    with http.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_hybrid", "source": "random", "fault": "FU1:1-2 open"})
        while True:
            ev = ws.receive_json()
            if ev["type"] == "flags_request":
                assert ev["flags"][0]["terminals"] == ["KM2:1", "KM2:5"]
                ws.send_json({"action": "flags", "id": ev["id"], "approve": False})
            if ev["type"] in ("done", "error"):
                break
    assert ev["type"] == "error" and "not confirmed" in ev["message"]


def test_hybrid_settles_a_pole_that_depends_on_flagged_wiring(monkeypatch):
    from tests.test_hybrid import FakeClient as HybridFake, true_data
    from tests.test_hybrid_checks import STAR_PINS, _swapped_star

    model = {**_swapped_star(true_data()), "uncertain": [{"terminals": STAR_PINS, "reason": "star wiring crosses"}]}
    monkeypatch.setattr(server, "client", lambda: HybridFake(None))
    monkeypatch.setattr(server.HybridSession, "read", lambda self, usage: (model, model["uncertain"], "test", b"png"))
    http = TestClient(server.app)
    seen = []
    with http.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_hybrid", "source": "random", "fault": "KM3:1-2 stuck_open"})
        while True:
            ev = ws.receive_json()
            seen.append(ev["type"])
            if ev["type"] == "flags_request":
                ws.send_json({"action": "flags", "id": ev["id"], "approve": True})
            if ev["type"] == "wiring_request":
                pick = next(i for i, o in enumerate(ev["options"]) if o["fault"] == "KM3:1-2 stuck_open")
                ws.send_json({"action": "wiring", "id": ev["id"], "choice": pick})
            if ev["type"] in ("done", "error"):
                break
    # the joint hypotheses settle the pole with a reading across it, so no human question is needed here
    assert "wiring_check" in seen and "wiring_request" not in seen
    assert ev["type"] == "done" and ev["diagnosis"]["part"] == "1-2" and ev["verdict"] == "correct"
    assert ev["wiring_check"]["verdict"].startswith("pole holds")
