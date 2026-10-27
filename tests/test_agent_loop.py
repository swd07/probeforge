"""Agent loop with a scripted fake model (no API calls)."""

import copy
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
        self.requests.append(copy.deepcopy(kwargs))
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
        FakeMessage(calls=[("measure_voltage", {"point_a": "1", "point_b": "N"})]),  # no update first: runs, counted
        FakeMessage(calls=[("update_hypotheses", HYP),  # step 3
                           ("submit_diagnosis", {"outcome": "diagnosed", "component": "FU1", "part": "1-2",
                                                 "failure_mode": "open", "confidence": 0.9,
                                                 "evidence": [{"step": 1, "type": "instrument_reading", "observation": "230 V before"},
                                                              {"step": 2, "type": "instrument_reading", "observation": "0 V after"}]})]),
    ])
    run, tb = loop.run_agent(fuse_circuit(netlist), client, model="muse-spark-1.3", effort="low")

    assert run.outcome == "diagnosed"
    assert run.turns == 4 and run.nudges == 1 and run.protocol_errors == 0
    assert run.missing_hypothesis_updates == 1
    assert tb.measurements == 3
    assert score(run.diagnosis, Fault("FU1", "open", "1-2")) == {"component_ok": True, "mode_ok": True, "part_ok": True}
    assert [h["step"] for h in tb.hypotheses_history] == [4]
    assert run.prompt_tokens == 4000 and run.completion_tokens == 400 and run.cost_usd > 0

    first = client.requests[0]
    assert first["reasoning_effort"] == "low"
    assert first["messages"][1]["content"][1]["type"] == "image_url"
    second = client.requests[1]["messages"][1]
    assert isinstance(second["content"], str) and "image was attached" in second["content"]
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
        "evidence": [{"step": 0, "type": "functional_test", "observation": "all lamps off"}]})])])
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


def test_at_most_three_measurements_per_turn(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    four = [("measure_voltage", {"point_a": net, "point_b": "N"}) for net in ("L1Q", "1", "2", "3")]
    client = FakeClient([
        FakeMessage(calls=four),
        FakeMessage(calls=[("update_hypotheses", HYP),
                           ("submit_diagnosis", {"outcome": "insufficient_information", "confidence": 0.1, "evidence": []})]),
    ])
    run, tb = loop.run_agent(fuse_circuit(netlist), client)
    assert tb.measurements == 3 and run.protocol_errors == 1
    assert "at most 3" in run.turn_log[0]["tool_calls"][3]["result"]["error"]


def test_image_every_turn_option(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    client = FakeClient([FakeMessage(calls=[("read_indicators", {})]),
                         FakeMessage(calls=[("submit_diagnosis", {"outcome": "insufficient_information",
                                                                  "confidence": 0.1, "evidence": []})])])
    loop.run_agent(fuse_circuit(netlist), client, image_once=False)
    assert client.requests[1]["messages"][1]["content"][1]["type"] == "image_url"


LEAKED = """<atem:function_calls>
<atem:invoke name="default.submit_diagnosis">
<atem:parameter name="confidence">0.9</atem:parameter>
<atem:parameter name="component">FU1</atem:parameter>
<atem:parameter name="evidence">[{"observation": "0 V after fuse", "step": 2, "type": "instrument_reading"}]</atem:parameter>
<atem:parameter name="failure_mode">open</atem:parameter>
<atem:parameter name="outcome">diagnosed</atem:parameter>
<atem:parameter name="part">1-2</atem:parameter>
</atem:invoke>
</atem:function_calls>"""


def test_tool_call_written_as_text_is_recovered(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    client = FakeClient([
        FakeMessage(calls=[("update_hypotheses", HYP), ("measure_voltage", {"point_a": "FU1:2", "point_b": "N"})]),
        FakeMessage(calls=[("update_hypotheses", HYP)]),
        FakeMessage(content=LEAKED),
    ])
    run, tb = loop.run_agent(fuse_circuit(netlist), client)
    assert run.outcome == "diagnosed" and run.recovered_text_calls == 1 and run.nudges == 0
    assert run.diagnosis["part"] == "1-2"
    assistant = run.messages[-2]
    assert assistant["tool_calls"][0]["id"] == "recovered_0" and run.messages[-1]["tool_call_id"] == "recovered_0"


def test_turn_budget_warnings(netlist, monkeypatch):
    monkeypatch.setattr(loop, "render_png", lambda n: b"png")
    client = FakeClient([FakeMessage(calls=[("read_indicators", {})]) for _ in range(8)])
    run, _ = loop.run_agent(fuse_circuit(netlist), client, max_turns=8)
    warnings = [m["content"] for m in run.messages if m["role"] == "user" and "turns left" in str(m["content"])]
    assert warnings == [loop.turns_left_warning(5), loop.turns_left_warning(2)]
    assert "at most 8 turns" in client.requests[0]["messages"][0]["content"]


def test_decisive_measurement():
    from probeforge.eval.trace import decisive_measurement

    def meas(step, a, b, volts):
        return {"step": step, "tool": "measure_voltage", "executed": True, "args": {"point_a": a, "point_b": b},
                "result": {"point_a": a, "point_b": b, "volts": volts}}

    def hyp(step, p, reason):
        return {"step": step, "hypotheses": [{"component": "SB1", "part": "11-12", "failure_mode": "stuck_open",
                                              "probability": p, "reason": reason},
                                             {"component": "KK1", "failure_mode": "tripped", "probability": 1 - p, "reason": ""}]}

    log = [meas(1, "1", "N", 230.0), meas(3, "2", "N", 230.0), meas(4, "3", "N", 0.0), meas(6, "SB1:11", "SB1:12", 230.0)]
    history = [hyp(2, 0.4, "wire 1 live"), hyp(5, 0.9, "wire 3 dead while 2 live"), hyp(7, 0.95, "confirmed")]
    diagnosis = {"outcome": "diagnosed", "component": "SB1", "part": "11-12", "failure_mode": "stuck_open"}
    d = decisive_measurement(log, history, diagnosis)
    assert d["step"] == 4 and d["reading"] == "3 -> N: 0.0 V"  # cited first in the reason ("wire 3 dead")
    assert (d["before"], d["after"], d["shared_with"]) == (0.4, 0.9, 1)
    # with the netlist, readings are compared with a healthy panel: net 3 should be live at rest
    from probeforge.sim import Netlist
    from tests.conftest import CIRCUIT_YAML

    log2 = [meas(1, "1", "N", 230.0), meas(3, "3", "N", 0.0), meas(4, "2", "N", 230.0), meas(6, "SB1:11", "SB1:12", 230.0)]
    history2 = [hyp(2, 0.4, "wire 1 live"), hyp(5, 0.9, "net 2 live (230 V) but net 3 dead"), hyp(7, 0.95, "confirmed")]
    d2 = decisive_measurement(log2, history2, diagnosis, Netlist.load(CIRCUIT_YAML))
    assert d2["reading"] == "3 -> N: 0.0 V" and d2["healthy"] == "230.0 V"  # abnormal beats first mention
    assert decisive_measurement(log, [], diagnosis) is None
    assert decisive_measurement(log, history, {"outcome": "insufficient_information"}) is None
