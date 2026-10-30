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


# ---------------------------------------------------------------- Responses API transport (D37)

import copy as _copy  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from probeforge.ats import agent_responses  # noqa: E402


class FakeItem:
    def __init__(self, d):
        self.d = d

    def model_dump(self, exclude_none=True):
        return _copy.deepcopy(self.d)


class FakeResponses:
    """Scripted Responses API: each step is a list of output items (reasoning, message, function_call)."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.requests.append(_copy.deepcopy(kw))
        out = self.script.pop(0)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200,
                                input_tokens_details=SimpleNamespace(cached_tokens=400),
                                output_tokens_details=SimpleNamespace(reasoning_tokens=150))
        return SimpleNamespace(output=[FakeItem(o) for o in out], usage=usage)


def reasoning(i):
    return {"type": "reasoning", "id": f"rs_{i}", "summary": [], "encrypted_content": f"ENC{i}"}


def call(i, name, args):
    return {"type": "function_call", "call_id": f"call_{i}", "name": name, "arguments": json.dumps(args), "status": "completed"}


def test_responses_transport_replays_statelessly(no_png):
    bench = scenario([Fault("TS", "open", "A-B")])
    client = FakeResponses([
        [reasoning(1), call(1, "measure_voltage", {"point_a": "TS:A", "point_b": "TS:B"})],
        [reasoning(2), {"type": "message", "content": [{"type": "output_text", "text": "thinking"}]}],  # no call: nudge
        [reasoning(3), call(2, "update_hypotheses", HYP),
         call(3, "submit_diagnosis", {"outcome": "diagnosed", "component": "TS", "part": "A-B", "failure_mode": "open",
                                      "confidence": 0.9, "evidence": [{"step": 1, "type": "instrument_reading",
                                                                      "observation": "208 V across A-B"}]})],
    ])
    run, tb = agent_responses.run_ats_agent_responses(bench, client)
    assert run.outcome == "diagnosed" and run.nudges == 1 and run.cached_tokens == 1200
    chat_system = ats_agent.build_initial_messages(AtsToolBox(scenario([Fault("TS", "open", "A-B")])))[0]["content"]
    for r in client.requests:  # stateless replay: nothing stored, reasoning returned, instructions every turn
        assert r["store"] is False and r["include"] == ["reasoning.encrypted_content"] and "previous_response_id" not in r
        assert r["instructions"] == chat_system and r["reasoning"] == {"effort": "low"} and r["tools"] == agent_responses.TOOLS
    first, second = client.requests[0]["input"], client.requests[1]["input"]
    assert any(c["type"] == "input_image" for c in first[0]["content"])  # the image only in the first request
    assert all(c["type"] == "input_text" for c in second[0]["content"]) and "image was attached" in second[0]["content"][0]["text"]
    # replay order: reasoning, its function_call, then our function_call_output with the same call_id
    assert [x.get("type", x.get("role")) for x in second[1:]] == ["reasoning", "function_call", "function_call_output"]
    assert second[1]["encrypted_content"] == "ENC1" and second[1]["summary"] == []
    assert second[3]["call_id"] == "call_1" and json.loads(second[3]["output"])["volts"] == 208.0
    third = client.requests[2]["input"]
    assert [x.get("type", x.get("role")) for x in third[4:]] == ["reasoning", "assistant", "user"]  # nudge after the message
    # same tools as the Chat agent, flattened
    assert [t["name"] for t in agent_responses.TOOLS] == [t["function"]["name"] for t in TOOL_SPECS]
    assert all(t["parameters"] == s["function"]["parameters"] for t, s in zip(agent_responses.TOOLS, TOOL_SPECS))


def test_a_reasoning_only_turn_is_followed_by_an_assistant_message():
    items = agent_responses.replay_items([reasoning(1)])
    assert items[0]["type"] == "reasoning" and items[1]["role"] == "assistant"
