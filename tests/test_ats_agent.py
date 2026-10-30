"""ATS agent profile (stage S3): the prompt leaks nothing about the fault (all 118 ATS faults), carries no hints
derived from the dev scenarios, the default (relay-panel) profile is byte-identical, and the loop works with a
scripted fake model (no API calls)."""

import hashlib
import inspect
import json
from pathlib import Path

import pytest
import yaml

from probeforge.ats import AtsBench
from probeforge.ats import agent as ats_agent
from probeforge.ats.faults import all_faults
from probeforge.ats.prompts import SYSTEM_PROMPT
from probeforge.ats.tools import TOOL_SPECS, AtsToolBox
from probeforge.faults.model import Fault
from tests.test_agent_loop import FakeClient, FakeMessage

ROOT = Path(__file__).resolve().parents[1]
CASES = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "scenarios" / "ats").glob("*.yaml"))]


@pytest.fixture
def no_png(monkeypatch):
    monkeypatch.setattr(ats_agent, "render_png", lambda netlist: b"png")


def scenario(faults) -> AtsBench:
    b = AtsBench(faults=faults)
    b.lose_utility()
    b.step(60)
    return b


def prompt_text(faults) -> tuple[str, str]:
    msgs = ats_agent.build_initial_messages(AtsToolBox(scenario(faults)))
    return msgs[0]["content"], msgs[1]["content"][0]["text"]


def test_prompt_does_not_reveal_the_fault_over_all_118_faults(no_png):
    healthy_system, healthy_user = prompt_text([])
    head = healthy_user.split("Step 0")[0]
    for fault in all_faults(AtsBench().n):
        system, user = prompt_text([fault])
        assert system == healthy_system and user.split("Step 0")[0] == head  # identical apart from the observation
        observation = user.split("Step 0")[1].split("Schematic text netlist")[0]
        for s in (str(fault), fault.target, json.dumps(fault.to_dict()), fault.mode):
            assert s not in observation, f"{fault}: {s!r} in the first observation"
        for c in CASES:
            assert c["description"] not in user and c["id"] not in user


def test_prompt_and_tool_specs_carry_no_dev_scenario_hints():
    """No dev fault location appears in the profile (the solenoid A-B is the only solenoid, so it is named)."""
    text = SYSTEM_PROMPT + json.dumps(TOOL_SPECS)
    parts = set()
    for c in CASES:
        for f in [c.get("fault"), c.get("root_cause"), *(c.get("faults") or []), *(c.get("also_accepted") or [])]:
            if f and f.get("part") and f["part"] != "A-B":
                parts.add(f["part"])
    assert parts
    for p in parts:
        assert p not in text, p
    for c in CASES:
        assert c["description"] not in text and c["symptom"] not in text


def test_default_profile_is_byte_identical():
    from probeforge.agent import prompts
    from probeforge.tools.toolbox import TOOL_SPECS as DEFAULT_SPECS

    sha = hashlib.sha256((inspect.getsource(prompts) + json.dumps(DEFAULT_SPECS, sort_keys=True)).encode()).hexdigest()
    assert sha[:12] == "a194ad85aaa1"  # the frozen "prompt" fingerprint (scripts/run_scenarios.py, frozen_hashes)


HYP = {"hypotheses": [{"component": "TS", "part": "A-B", "failure_mode": "open", "probability": 0.8, "reason": "208 V"},
                      {"component": "TS", "part": "", "failure_mode": "jammed", "probability": 0.2, "reason": "?"}]}


def test_ats_session_with_a_fake_model(no_png):
    bench = scenario([Fault("TS", "open", "A-B")])
    client = FakeClient([
        FakeMessage(content="thinking"),  # nudge
        FakeMessage(calls=[("read_event_log", {}), ("measure_voltage", {"point_a": "TS:A", "point_b": "TS:B"})]),
        FakeMessage(calls=[("update_hypotheses", HYP), ("isolate_sources", {"reason": "resistance check"})]),
        FakeMessage(calls=[("measure_resistance", {"point_a": "TS:A", "point_b": "TS:B"}),
                           ("measure_resistance", {"point_a": "TS:8", "point_b": "TS:9"}),
                           ("measure_resistance", {"point_a": "TS:71", "point_b": "TS:72"}),
                           ("measure_resistance", {"point_a": "TS:6", "point_b": "TS:7"})]),  # 4th: refused
        FakeMessage(calls=[("update_hypotheses", HYP), ("manual_operation_check", {"reason": "mechanism"}),
                           ("repeat_transfer_attempt", {"reason": "retry", "evidence_steps": [3]})]),
        FakeMessage(calls=[("submit_diagnosis", {
            "outcome": "diagnosed", "component": "TS", "part": "A-B", "failure_mode": "open", "confidence": 0.9,
            "evidence": [{"step": 2, "type": "instrument_reading", "observation": "208 V across A-B"},
                         {"step": 5, "type": "instrument_reading", "observation": "A-B open"}]})]),
    ])
    run, tb = ats_agent.run_ats_agent(bench, client)
    assert run.outcome == "diagnosed" and run.diagnosis["part"] == "A-B" and run.nudges == 1
    assert run.protocol_errors == 1  # the 4th reading in one turn
    assert client.requests[0]["reasoning_effort"] == "low" and client.requests[0]["tools"] == TOOL_SPECS
    assert isinstance(client.requests[1]["messages"][1]["content"], str)  # image only in the first request
    log = {e["step"]: e for e in tb.log}
    assert log[2]["result"]["volts"] == 208.0 and log[5]["result"]["ohms"] == "open"
    assert log[4]["result"]["approved_by_human"] == "approval"  # batch approver: approval tier yes
    assert "denied" in tb.log[-2]["result"]["error"] or "blocked" in tb.log[-2]["result"]  # repeat: not under isolation
    assert tb.policy.stats.approval_requests == 2
