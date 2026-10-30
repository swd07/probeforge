"""Web backend on the ATS bench: an engineer session and an agent session (scripted fake model) over the WebSocket,
each through the diagnosis and the authorized intervention to "Transfer verified". The fault reaches the browser only
in the "done" event."""

import json

import pytest
from fastapi.testclient import TestClient

from probeforge.ats import agent as ats_agent
from probeforge.eval.spend import SpendLedger
from probeforge.server import app as server
from probeforge.server import ats
from tests.test_agent_loop import FakeClient, FakeMessage


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json")
    monkeypatch.setattr(ats, "SpendLedger", lambda: ledger)
    monkeypatch.setattr(ats, "ENGINEER_DIR", tmp_path / "engineer_traces" / "ats")
    monkeypatch.setattr(ats, "warm_signatures", lambda: None)
    monkeypatch.setattr(ats, "catalog_signatures", lambda: {})  # twins: not needed here (15 s to compute)
    monkeypatch.setattr(ats_agent, "render_png", lambda n: b"png")
    return tmp_path


def until(ws, kind: str, events: list, answer_approvals: bool = True) -> dict:
    while True:
        ev = ws.receive_json()
        events.append(ev)
        if ev["type"] == "approval_request" and answer_approvals:
            ws.send_json({"action": "approval", "id": ev["id"], "approve": True})
        if ev["type"] == kind:
            return ev
        assert ev["type"] != "error", ev


def tool(ws, events, name, args, kind="tool") -> dict:
    ws.send_json({"action": "tool", "name": name, "args": args})
    return until(ws, kind, events)


def test_ats_meta_and_drawing():
    http = TestClient(server.app)
    meta = http.get("/api/ats/meta").json()
    assert meta["neutral"] == "NN" and len(meta["scenarios"]) == 12
    assert all(set(s) == {"id", "symptom"} for s in meta["scenarios"])  # descriptions would name the fault
    assert meta["flow"][-1] == "Transfer verified" and meta["ups_autonomy_s"] == 600
    assert {"action", "tier", "condition"} == set(meta["limits"][0])
    svg = http.get("/api/ats/schematic").text
    assert svg.startswith("<svg") and 'data-terminal="TS:A"' in svg and "Not the official drawing" in svg


def test_engineer_session_through_the_intervention_to_transfer_verified():
    http = TestClient(server.app)
    events: list = []
    with http.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_manual", "bench": "ats", "source": "scenario", "scenario": "a1_coil_open",
                      "engineer": "test"})
        s = until(ws, "session", events)
        assert s["bench"] == "ats" and s["panel"]["display"] == "Transfer Failure" and s["panel"]["flow"] == 0
        r = tool(ws, events, "measure_voltage", {"point_a": "TS:A", "point_b": "TS:B"})
        assert r["result"]["volts"] == 208.0 and r["probes"][0]["term_a"] == "TS:A" and r["panel"]["flow"] == 1
        assert "same point" in tool(ws, events, "measure_voltage", {"point_a": "TS:A", "point_b": "TS:A"})["result"]["error"]
        iso = tool(ws, events, "isolate_sources", {"reason": "ohmmeter"})
        assert iso["panel"]["isolated"] and any(e["type"] == "approval_request" and not e["strong"] for e in events)
        r = tool(ws, events, "measure_resistance", {"point_a": "TS:A", "point_b": "TS:B"})
        assert r["result"]["ohms"] == "open"
        ws.send_json({"action": "tool", "name": "submit_diagnosis", "args": {
            "outcome": "diagnosed", "component": "TS", "part": "A-B", "failure_mode": "open", "confidence": 0.9,
            "evidence": [{"step": 4, "type": "instrument_reading", "observation": "A-B open"}]}})
        done = until(ws, "done", events)
        assert done["verdict"] == "correct" and done["fault"] == "TS:A-B open" and done["intervention"]
        assert done["panel"]["flow"] == 3  # awaiting authorized intervention
        before_done = json.dumps(events[:-1])
        assert "TS:A-B open" not in before_done and "coil_open" not in before_done.replace("a1_coil_open", "")
        until(ws, "saved", events)
        tool(ws, events, "perform_action", {"action": "replace_coil", "target": "TS:A-B", "reason": "coil open"})
        ev = tool(ws, events, "measure_resistance", {"point_a": "TS:A", "point_b": "TS:B"})
        assert ev["result"]["ohms"] == 30.0
        # restoring after the Transfer Failure is a strong approval: refused without a cited reading
        r = tool(ws, events, "restore_sources", {"reason": "verify"})
        assert r["verdict"] == "needs_strong_approval" and not r["executed"] and "evidence_steps" in r["result"]["error"]
        tool(ws, events, "restore_sources", {"reason": "verify", "evidence_steps": [ev["step"]]}, kind="verified")
        strong = [e for e in events if e["type"] == "approval_request" and e["strong"]]
        assert len(strong) == 1 and strong[0]["evidence"][0]["step"] == ev["step"]
        last_tool = [e for e in events if e["type"] == "tool"][-1]
        assert last_tool["panel"]["flow"] == 5 and last_tool["panel"]["load_powered"] and last_tool["panel"]["position"] == "Emergency"


def test_agent_session_then_intervention_with_policy_fact():
    hyp = {"hypotheses": [{"component": "TS", "part": "17-16", "failure_mode": "stuck_open", "probability": 0.9, "reason": "r"}]}
    client = FakeClient([
        FakeMessage(calls=[("measure_voltage", {"point_a": "TS:20", "point_b": "TS:21"})]),  # step 1: load powered
        FakeMessage(calls=[("update_hypotheses", hyp),
                           ("isolate_sources", {"reason": "load on UPS", "evidence_steps": [1]})]),  # step 3: strong
        FakeMessage(calls=[("submit_diagnosis", {
            "outcome": "diagnosed", "component": "TS", "part": "17-16", "failure_mode": "stuck_open", "confidence": 0.8,
            "evidence": [{"step": 1, "type": "instrument_reading", "observation": "208 V on the load"}]})]),
    ])
    import probeforge.server.app as app_module

    orig = app_module.client
    app_module.client = lambda: client
    try:
        http = TestClient(server.app)
        events: list = []
        with http.websocket_connect("/ws") as ws:
            ws.send_json({"action": "start", "bench": "ats", "source": "scenario", "scenario": "x1_aux14b_open", "effort": "low"})
            while True:
                ev = ws.receive_json()
                events.append(ev)
                if ev["type"] == "approval_request":
                    # the policy contradicts the agent's reason on the card: the generator feeds the load
                    assert ev["strong"] and ev["agent_reason"] == "load on UPS"
                    assert ev["facts"] == ["Load is currently powered from the Emergency source; isolation will de-energize it."]
                    ws.send_json({"action": "approval", "id": ev["id"], "approve": False})
                if ev["type"] == "done":
                    break
                assert ev["type"] != "error", ev
            assert ev["verdict"] == "correct" and ev["panel"]["load_powered"]
            # the intervention after the agent: the human may act through the same policy
            r = tool(ws, events, "read_panel", {})
            assert r["executed"] and r["result"]["load_powered"]
    finally:
        app_module.client = orig
