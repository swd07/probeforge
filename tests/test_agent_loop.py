"""Agent loop with a scripted fake model (no API calls)."""

import json
from types import SimpleNamespace

from probeforge.agent import loop
from probeforge.eval.scoring import score
from probeforge.faults import Fault
from probeforge.sim import Circuit


class FakeMessage:
    def __init__(self, content=None, calls=()):
        self.content = content
        self.tool_calls = [
            SimpleNamespace(id=f"call_{i}_{name}", function=SimpleNamespace(name=name, arguments=json.dumps(args)))
            for i, (name, args) in enumerate(calls)
        ] or None

    def model_dump(self, exclude_none=True):
        d = {"role": "assistant"}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in self.tool_calls
            ]
        return d


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        msg = self.script.pop(0)
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=100, prompt_tokens_details=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


def fuse_circuit(netlist) -> Circuit:
    c = Circuit(netlist)
    c.apply_fault(Fault("FU1", "open", "1-2"))
    c.set_power(True)
    return c


HYP = {"hypotheses": [{"component": "FU1", "part": "1-2", "failure_mode": "open", "probability": 0.9, "reason": "0 V"}]}


def test_full_session_with_nudge_and_protocol_error(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    client = FakeClient([
        FakeMessage(content="Let me think about this."),  # no tool call -> nudge
        FakeMessage(calls=[("measure_voltage", {"point_a": "FU1:1", "point_b": "N"}),
                           ("measure_voltage", {"point_a": "FU1:2", "point_b": "N"})]),  # steps 1, 2 (parallel ok)
        FakeMessage(calls=[("measure_voltage", {"point_a": "1", "point_b": "N"})]),  # no update first -> error
        FakeMessage(calls=[("update_hypotheses", HYP),  # step 3
                           ("submit_diagnosis", {"outcome": "diagnosed", "component": "FU1", "part": "1-2",
                                                 "failure_mode": "open", "confidence": 0.9,
                                                 "evidence": [{"step": 1, "observation": "230 V before"},
                                                              {"step": 2, "observation": "0 V after"}]})]),
    ])
    run, tb = loop.run_agent(fuse_circuit(netlist), client, model="muse-spark-1.3", effort="low")

    assert run.outcome == "diagnosed"
    assert run.turns == 4 and run.nudges == 1 and run.protocol_errors == 1
    assert tb.measurements == 2
    assert score(run.diagnosis, Fault("FU1", "open", "1-2")) == {"component_ok": True, "mode_ok": True, "part_ok": True}
    assert [h["step"] for h in tb.hypotheses_history] == [3]
    assert run.prompt_tokens == 4000 and run.completion_tokens == 400 and run.cost_usd > 0

    first = client.requests[0]
    assert first["reasoning_effort"] == "low"
    assert first["messages"][1]["content"][1]["type"] == "image_url"
    assert "tool_choice" not in first

    # every assistant tool call is followed by exactly its tool results (Meta API ordering rule)
    msgs = run.messages
    for i, m in enumerate(msgs):
        if m["role"] == "assistant" and m.get("tool_calls"):
            ids = [c["id"] for c in m["tool_calls"]]
            following = [x["tool_call_id"] for x in msgs[i + 1 : i + 1 + len(ids)]]
            assert following == ids
    nudge = msgs[3]
    assert nudge["role"] == "user" and "Continue" in nudge["content"]


def test_max_turns_without_diagnosis(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    client = FakeClient([FakeMessage(calls=[("read_indicators", {})]) for _ in range(5)])
    run, _ = loop.run_agent(fuse_circuit(netlist), client, max_turns=5)
    assert run.outcome == "no_diagnosis" and run.turns == 5


def test_gives_up_after_repeated_text_replies(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    client = FakeClient([FakeMessage(content="hmm") for _ in range(10)])
    run, _ = loop.run_agent(fuse_circuit(netlist), client)
    assert run.outcome == "no_diagnosis" and run.nudges == 4


def test_insufficient_information_outcome(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    client = FakeClient([FakeMessage(calls=[("submit_diagnosis", {"outcome": "insufficient_information",
                                                                  "confidence": 0.3, "evidence": []})])])
    run, _ = loop.run_agent(fuse_circuit(netlist), client)
    assert run.outcome == "insufficient_information"
    assert score(run.diagnosis, Fault("FU1", "open", "1-2"))["component_ok"] is False


def test_initial_observation_is_citable_as_step_0(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    client = FakeClient([FakeMessage(calls=[("submit_diagnosis", {
        "outcome": "diagnosed", "component": "FU1", "failure_mode": "open", "confidence": 0.6,
        "evidence": [{"step": 0, "observation": "all lamps off"}]})])])
    run, tb = loop.run_agent(fuse_circuit(netlist), client)
    assert run.outcome == "diagnosed" and tb.policy.stats.blocked == 0
    assert tb.log[0]["step"] == 0


def test_bad_json_arguments_reported(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    bad = FakeMessage(calls=[("read_indicators", {})])
    bad.tool_calls[0].function.arguments = "{not json"
    client = FakeClient([bad, FakeMessage(calls=[("submit_diagnosis", {"outcome": "insufficient_information",
                                                                       "confidence": 0.1, "evidence": []})])])
    run, _ = loop.run_agent(fuse_circuit(netlist), client)
    assert run.protocol_errors == 1
    assert "not a valid JSON" in run.messages[3]["content"]


def test_api_error_keeps_partial_trace(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")

    class Boom(FakeClient):
        def create(self, **kwargs):
            raise RuntimeError("HTTP 500")

    run, _ = loop.run_agent(fuse_circuit(netlist), Boom([]))
    assert run.outcome == "error" and "HTTP 500" in run.error
