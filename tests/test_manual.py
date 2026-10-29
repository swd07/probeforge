"""Manual (engineer) mode, the human / agent / baseline comparison, engineer traces and the spend guard."""

import json

import pytest
from fastapi.testclient import TestClient

from probeforge.agent import loop
from probeforge.eval.engineer import engineer_reference, load_engineer_traces
from probeforge.eval.spend import SpendLedger, SpendLimitError
from probeforge.faults import Fault
from probeforge.server import app as server
from tests.test_agent_loop import FakeClient, FakeMessage


@pytest.fixture
def env(monkeypatch, tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json")
    monkeypatch.setattr(server, "ledger", lambda: ledger)
    monkeypatch.setattr(server, "ENGINEER_DIR", tmp_path / "engineer_traces")
    monkeypatch.setattr(server, "COMPARE_DIR", tmp_path / "compare")
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    monkeypatch.setattr(server, "client", lambda: FakeClient([
        FakeMessage(calls=[("measure_voltage", {"point_a": "FU1:2", "point_b": "N"})]),
        FakeMessage(calls=[("submit_diagnosis", {"outcome": "diagnosed", "component": "FU1", "part": "1-2",
                                                 "failure_mode": "open", "confidence": 0.9,
                                                 "evidence": [{"step": 1, "type": "instrument_reading", "observation": "0 V"}]})]),
    ]))
    return tmp_path, ledger


def until(ws, *types):
    events = []
    while True:
        ev = ws.receive_json()
        events.append(ev)
        if ev["type"] in types:
            return events


def test_manual_session_records_trace_and_compares(env):
    tmp, ledger = env
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_manual", "source": "scenario", "scenario": "s01", "engineer": "Ivan P."})
        session = until(ws, "session")[-1]
        assert session["mode"] == "manual" and session["engineer"] == "Ivan P."

        def act(name, args):
            ws.send_json({"action": "tool", "name": name, "args": args})
            return until(ws, "tool")[-1]

        blocked = act("measure_resistance", {"point_a": "FU1:1", "point_b": "FU1:2"})  # step 1: power is on
        assert blocked["verdict"] == "block" and blocked["result"]["blocked"]
        v = act("measure_voltage", {"point_a": "L1Q", "point_b": "1"})  # step 2: picked a wire and a net
        assert v["result"]["volts"] == 230.0 and v["probes"][0]["net_b"] == "1"
        act("set_power", {"on": False})  # step 3
        r = act("measure_resistance", {"point_a": "FU1:1", "point_b": "FU1:2"})  # step 4
        assert r["result"]["ohms"] == "open"
        ws.send_json({"action": "tool", "name": "update_hypotheses", "args": {"hypotheses": []}})  # not a manual tool
        assert until(ws, "error")[-1]["message"].startswith("tool 'update_hypotheses'")

        ws.send_json({"action": "tool", "name": "submit_diagnosis", "args": {
            "outcome": "diagnosed", "component": "FU1", "part": "1-2", "failure_mode": "open", "confidence": 0.95,
            "evidence": [{"step": 2, "type": "instrument_reading", "observation": "230 V across FU1"},
                         {"step": 4, "type": "instrument_reading", "observation": "FU1 open"}]}})
        events = until(ws, "saved")
        done = next(e for e in events if e["type"] == "done")
        assert done["mode"] == "manual" and done["verdict"] == "correct" and done["fault"] == "FU1:1-2 open"
        assert done["measurements"] == 2 and done["policy_blocked"] == 1 and done["cost_usd"] == 0.0
        assert "FU1:1-2 open" not in json.dumps([e for e in events if e["type"] != "done" and e["type"] != "saved"])

        ws.send_json({"action": "compare"})
        result = until(ws, "compare")[-1]

    cols = result["columns"]
    assert set(cols) == {"human", "agent", "baseline"}
    assert cols["human"]["verdict"] == "correct" and cols["human"]["blocked"] == 1
    assert cols["human"]["sequence"][0].startswith("blocked: measure_resistance")
    assert cols["baseline"]["verdict"] == "correct" and cols["baseline"]["cost_usd"] == 0
    assert cols["agent"]["verdict"] == "correct" and cols["agent"]["measurements"] == 1
    assert ledger.total > 21.0  # the compare agent run was recorded

    files = list((tmp / "engineer_traces").glob("*.json"))
    assert len(files) == 1 and files[0].name.startswith("FU1-1-2-open__Ivan-P")
    trace = json.loads(files[0].read_text(encoding="utf-8"))
    for key in ("runner", "outcome", "diagnosis", "measurements", "redundant_measurements", "policy", "tool_log",
                "turn_log", "hypotheses_history", "tokens", "cost_usd", "seconds"):
        assert key in trace  # same format as agent traces
    assert trace["runner"] == "human" and trace["engineer"] == "Ivan P." and trace["verdict"] == "correct"
    assert trace["fault"] == {"component": "FU1", "mode": "open", "part": "1-2"}

    refs = load_engineer_traces(tmp / "engineer_traces")
    ref = engineer_reference(Fault("FU1", "open", "1-2"), refs)
    assert ref["engineer"] == "Ivan P." and ref["measurements"] == 2 and ref["blocked"] == 1
    assert list((tmp / "compare").glob("*.json"))


def test_manual_approval_flow(env):
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_manual", "source": "scenario", "scenario": "s03"})
        until(ws, "session")
        ws.send_json({"action": "tool", "name": "perform_action",
                      "args": {"action": "reset_protection", "target": "KK1", "reason": "check after cooling"}})
        req = until(ws, "approval_request")[-1]
        assert req["agent_reason"] == "check after cooling"
        ws.send_json({"action": "approval", "id": req["id"], "approve": True})
        ev = until(ws, "tool")[-1]
        assert ev["result"]["approved_by_human"] and not ev["panel"]["lamps"]["Fault"]


def test_spend_ledger(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json")
    assert ledger.total == 21.0
    ledger.check(80.0)  # 101 <= 110 (130 total minus the 20 reserved for the demo)
    with pytest.raises(SpendLimitError):
        ledger.check(90.0)
    ledger.check(90.0, force=True)
    assert ledger.record(1.5, "test") == 22.5
    assert SpendLedger(tmp_path / "spend.json").total == 22.5  # persisted, not re-initialized
    data = json.loads((tmp_path / "spend.json").read_text())
    assert [e["usd"] for e in data["entries"]] == [21.0, 1.5]


def test_ui_agent_run_refused_over_limit(env):
    tmp, ledger = env
    ledger.record(109.0, "pretend")  # 130 total: even the demo reserve is used up
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "start", "source": "scenario", "scenario": "s01"})
        ev = until(ws, "error", "done")[-1]
    assert ev["type"] == "error" and "demo runs are stopped" in ev["message"]


def test_spend_ledger_demo_reserve_and_daily_cap(tmp_path, monkeypatch):
    from probeforge.eval import spend

    monkeypatch.setattr(spend, "DEMO_DAILY_USD", 5.0)
    ledger = SpendLedger(tmp_path / "spend.json")
    ledger.record(88.0, "batches")  # 109 total: batches are nearly at their 110 cap
    with pytest.raises(SpendLimitError):
        ledger.check(2.0)
    ledger.check(2.0, demo=True)  # live runs may use the reserve
    ledger.record(4.5, "ui run", demo=True)
    assert ledger.demo_today() == 4.5
    with pytest.raises(SpendLimitError, match="daily cap"):
        ledger.check(1.0, demo=True)


def test_cancel_tells_the_browser_once_for_every_session_type(env, monkeypatch):
    from tests.test_hybrid import FakeClient as HybridFake

    fault = Fault("FU1", "open", "1-2")
    sessions = [server.AgentSession(fault, "test", "low", None), server.HybridSession(fault, "test", "saved", None),
                server.ManualSession(fault, "test", "eng", None)]
    for s in sessions:
        events = []
        s.emit = events.append
        s.cancel()
        s.cancel()  # a second click does not repeat it
        assert [e["type"] for e in events] == ["stopped"] and events[0]["mode"] == s.mode
    quiet = []
    s = server.ManualSession(fault, "test", "eng", quiet.append)
    s.cancel(notify=False)  # replaced by a new session: the browser already reset
    done = server.ManualSession(fault, "test", "eng", quiet.append)
    done.done = True
    done.cancel()  # already finished: nothing to end
    assert quiet == []

    # a worker thread that sees the cancel afterwards does not send an error (it could land in the next session)
    monkeypatch.setattr(server, "client", lambda: HybridFake(None))
    for s in (server.AgentSession(fault, "test", "low", None), server.HybridSession(fault, "test", "saved", None)):
        events = []
        s.emit = events.append
        s.cancel()
        s.run()
        assert s.done and not [e for e in events if e["type"] == "error"], events


def test_end_session_then_tool_call_gives_an_error_not_silence(env):
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "tool", "name": "read_indicators", "args": {}})  # no session yet
        assert "No engineer session" in until(ws, "error")[-1]["message"]
        ws.send_json({"action": "start_manual", "source": "scenario", "scenario": "s01", "engineer": "T"})
        until(ws, "session")
        ws.send_json({"action": "stop"})
        stopped = until(ws, "stopped", "error")[-1]
        assert stopped["type"] == "stopped" and stopped["mode"] == "manual"
        ws.send_json({"action": "tool", "name": "measure_voltage", "args": {"point_a": "FU1:1", "point_b": "N"}})
        events = until(ws, "error", "tool")
        assert events[-1]["type"] == "error" and "ended" in events[-1]["message"]


def test_tool_call_on_a_finished_session_gives_an_error(env):
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_json({"action": "start_manual", "source": "scenario", "scenario": "s01", "engineer": "T"})
        until(ws, "session")
        ws.send_json({"action": "tool", "name": "submit_diagnosis", "args": {
            "outcome": "insufficient_information", "confidence": 0.1,
            "evidence": [{"step": 0, "type": "functional_test", "observation": "panel at the start"}]}})
        until(ws, "done")
        ws.send_json({"action": "tool", "name": "read_indicators", "args": {}})
        events = until(ws, "error", "tool")
        assert events[-1]["type"] == "error" and "finished" in events[-1]["message"]
