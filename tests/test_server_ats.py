"""Web backend on the ATS bench: an engineer session and an agent session (scripted fake model) over the WebSocket,
each through the diagnosis and the authorized intervention to "Transfer verified". The fault reaches the browser only
in the "done" event."""

import json

import pytest
from fastapi.testclient import TestClient

from probeforge.ats import agent as ats_agent
from probeforge.eval.spend import SpendLedger
from probeforge.server import ui_runs
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
        runs = ui_runs.faults_run("ats")  # the local UI run list (D44), written after the diagnosis
        assert [(r["mode"], r["faults"], r["ended"]) for r in runs] == [("manual", ["TS:A-B open"], "diagnosis")]
        u = done["ups_at_diagnosis"]  # UPS time left when the diagnosis was submitted, the load not lost yet
        assert not u["load_lost"] and 0 < u["ups_left_s"] < 600 and not done["panel"]["load_lost"]
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
                    # the cited reading is on the card while the agent runs (its toolbox is bound only afterwards)
                    assert [e["step"] for e in ev["evidence"]] == [1] and "TS:20 to TS:21" in ev["evidence"][0]["text"]
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


def test_hybrid_session_on_a_saved_transcription(monkeypatch, tmp_path):
    """Hybrid v2 on the ATS bench over the WebSocket: the transcription card data, the model check, the planner's next
    step before every reading (the step then taken), human approvals, and the fault only in "done". A perfect read
    stands in for the saved transcription (same netlist as our redrawing: about 12 s of candidate simulation)."""
    import threading

    from probeforge.ats.hybrid.read import build
    from tests.test_ats_hybrid import perfect_transcription

    data = build(perfect_transcription())
    record = {"id": "test_read", "label": "Test read", "run_id": "test_run", "recorded": "2026-10-31 00:00", "reads": 1,
              "repairs": 0, "cost_usd": 0.0, "seconds": 1.0, "read_quality": [], "disclosure": "test",
              "healthy": {"ok": True, "attempts": []}, "flags": [], "data": data, "raw": {}}
    monkeypatch.setattr(ats.transcriptions, "load", lambda tid: record)
    ready = threading.Event()
    ready.set()
    monkeypatch.setattr(ats, "warm_transcription", lambda tid: ready)
    monkeypatch.setattr(ats, "PLAN_PAUSE_S", 0.01)  # the display pause is counted and excluded from reported times
    monkeypatch.setenv("PROBEFORGE_OFFLINE", "1")
    monkeypatch.setattr(ats, "COMPARE_DIR", tmp_path / "compare")
    monkeypatch.setattr(server, "client", lambda: (_ for _ in ()).throw(RuntimeError("no key")))  # no explanation call
    http = TestClient(server.app)
    events: list = []
    with http.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_hybrid", "bench": "ats", "source": "scenario", "scenario": "a1_coil_open",
                      "schematic": "test_read"})
        s = until(ws, "session", events)
        assert s["mode"] == "hybrid" and s["bench"] == "ats"
        t = until(ws, "ats_transcription", events)
        assert t["run_id"] == "test_run" and t["recorded"] and t["attempts"] == []
        assert until(ws, "model_check", events)["ok"]
        done = until(ws, "done", events)
        # Compare: this session is the hybrid column; the baseline re-runs; no engineer trace exists; the agent
        # re-run is not started in offline mode (its column says so)
        ws.send_json({"action": "compare"})
        cmp = until(ws, "compare", events)
    assert done["mode"] == "hybrid" and done["verdict"] == "correct" and done["fault"] == "TS:A-B open"
    assert done["transcription"].startswith("Test read (test_run")
    cols = cmp["columns"]
    assert cmp["own"] == "hybrid" and cols["hybrid"]["approvals_by"] == "answered live in this session"
    assert cols["baseline"]["verdict"] == "correct" and cols["baseline"]["approvals_by"] == "batch rules"
    assert cols["human"]["missing"] == "no engineer trace recorded for this fault"
    assert cols["agent"]["missing"] == "agent not run (offline mode)"
    # twins are named instead of a split confidence
    assert done["diagnosis_text"] == "TS A-B open or burnt (no reading separates them; same repair)" and done["twins_named"]
    assert cols["hybrid"]["diagnosis"] == done["diagnosis_text"] and cols["hybrid"]["confidence"] is None
    pauses = len([e for e in events if e["type"] == "next_step" and e["tool"] != "submit_diagnosis"])
    assert done["display_pause_s"] == pytest.approx(0.01 * pauses)
    assert "identical here" in cmp["note"] and "exclude the UI display pause" in cmp["note"]
    plans = [e for e in events if e["type"] == "next_step"]
    tools = [e for e in events if e["type"] == "tool" and e["tool"] != "update_hypotheses"]
    assert plans and plans[-1]["tool"] == "submit_diagnosis"
    for p in plans:  # every plan is the next step taken
        later = [e for e in tools if events.index(e) > events.index(p)]
        assert later and later[0]["tool"] == p["tool"]
        if p["tool"] == "measure_voltage":
            assert later[0]["args"]["point_a"] == p["points"][0] and p["terminals"]
    assert any(e["type"] == "approval_request" for e in events)  # isolation for the resistance check, answered by the human
    before_done = events[:events.index(done)]
    assert not any("fault" in e or "truth_live_nets" in e for e in before_done)


def test_ats_meta_lists_saved_transcriptions_and_the_live_read_estimate(monkeypatch):
    monkeypatch.setattr(ats, "warm_transcription", lambda tid: None)
    meta = TestClient(server.app).get("/api/ats/meta").json()
    ids = [t["id"] for t in meta["transcriptions"]]
    assert meta["default_transcription"] in ids and all(t["run_id"] and t["recorded"] for t in meta["transcriptions"])
    assert "$" in meta["live_read"]["estimate"] and "minutes" in meta["live_read"]["estimate"]


def test_engineer_suggestion_replays_the_engineers_steps_and_never_reads_the_fault(tmp_path):
    """The suggestion is the info-gain planner on our redrawing after the engineer's own steps: the same plan the
    baseline makes after the same steps, unchanged when the bench's injected fault is swapped; the saved trace is
    marked assisted."""
    from types import SimpleNamespace

    from probeforge.ats.infogain import AtsInfoGain
    from probeforge.ats.nextstep import planned_next
    from probeforge.faults.model import Fault

    fault = Fault("TS", "open", "A-B")
    plans: list = []
    base = AtsInfoGain(ats._outage([fault]), ats.NETLIST, model_key="true",
                       on_update=lambda pl, step: plans.append((len(pl.steps), planned_next(pl))))
    base.run()
    tb = ats.AtsToolBox(ats._outage([fault]))
    tb.initial_observation()
    for s in base.steps:
        k = len([e for e in tb.log[1:] if e["executed"] and e["tool"] not in ats.SKIP_IN_REPLAY])
        want = next(p for n, p in plans if n == k)
        got = ats.suggest_next(tb)
        assert (got["tool"], got["args"]) == (want["tool"], want["args"])
        # the bench's fault is never read: the same log on a bench with another fault gives the same suggestion
        swapped = SimpleNamespace(log=tb.log, action_s=tb.action_s, step=tb.step,
                                  bench=SimpleNamespace(isolated=tb.bench.isolated, faults=[Fault("TS", "jammed")]))
        assert ats.suggest_next(swapped) == got
        tb.call(s.tool, s.args)

    http = TestClient(server.app)
    events: list = []
    with http.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_manual", "bench": "ats", "source": "scenario", "scenario": "a1_coil_open",
                      "engineer": "test"})
        until(ws, "session", events)
        ws.send_json({"action": "suggest"})
        sug = until(ws, "suggestion", events)
        assert sug["tool"] == "measure_voltage" and sug["terminals"] and len(sug["outcomes"]) >= 2
        ws.send_json({"action": "tool", "name": "submit_diagnosis", "args": {
            "outcome": "insufficient_information", "confidence": 0.0,
            "evidence": [{"step": 0, "type": "functional_test", "observation": "panel"}]}})
        until(ws, "saved", events)
    saved = json.loads(next((tmp_path / "engineer_traces" / "ats").glob("*.json")).read_text(encoding="utf-8"))
    assert saved["assisted"] is True and saved["suggestions"][0]["tool"] == "measure_voltage"
