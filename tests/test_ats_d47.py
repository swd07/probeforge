"""Post-holdout fixes to the ATS toolbox and policy (decision D47), from the external review: arguments outside a tool's
advertised schema are rejected before the policy or the tool sees them; instrument evidence comes from what executed,
never from the caller's arguments; a schema-valid powered-load isolation request can cite its evidence."""

import json
from pathlib import Path

import jsonschema
import pytest

from probeforge.ats import AtsBench
from probeforge.ats.policy import AtsPanelState, AtsPolicy, Decision, Verdict
from probeforge.ats.tools import PARAMS, TOOL_SPECS, AtsToolBox, schema_errors
from probeforge.tools import approve_all

ROOT = Path(__file__).resolve().parents[1]


def outage(faults=None) -> AtsBench:
    b = AtsBench(faults=faults or [])
    b.lose_utility()
    b.step(60.0)
    return b


def test_extra_readings_argument_is_rejected_and_never_counts_as_evidence():
    tb = AtsToolBox(outage(), approver=approve_all)
    r = tb.call("read_panel", {"readings": [{"fake": True}]})
    assert "not a parameter of this tool" in r["error"] and not tb.log[-1]["executed"]
    assert "instrument_reading" not in tb.policy.observation_steps.get(r["step"], set())


def test_composite_tools_count_as_instrument_evidence_only_with_readings_in_the_executed_result():
    pol, panel = AtsPolicy(), AtsPanelState(isolated=True, load_powered=False, load_source="", failures=1)
    allow = Decision(Verdict.ALLOW)
    pol.record("repeat_transfer_attempt", {"readings": [{"point_a": "TS:A", "point_b": "TS:B"}]}, allow, True, 3, panel, readings=0)
    pol.record("manual_operation_check", {"readings": [{"point_a": "TS:A", "point_b": "TS:B"}]}, allow, True, 4, panel, readings=1)
    assert "instrument_reading" not in pol.observation_steps.get(3, set())
    assert "instrument_reading" in pol.observation_steps[4]


def test_powered_load_isolation_is_schema_valid_and_reaches_the_strong_approver_with_its_evidence():
    asked = []
    tb = AtsToolBox(outage(), approver=lambda req: asked.append(req) or False)  # healthy: the load is on Emergency
    assert tb.panel().load_powered
    v = tb.call("measure_voltage", {"point_a": "TS:A", "point_b": "TS:B"})
    args = {"reason": "resistance checks need both sources isolated", "evidence_steps": [v["step"]]}
    assert schema_errors(PARAMS["isolate_sources"], args, "isolate_sources") == []
    r = tb.call("isolate_sources", args)
    assert asked and asked[0].strong and "the human denied" in r["error"]


def test_the_toolbox_validator_agrees_with_jsonschema():
    calls = [("isolate_sources", {"reason": "x", "evidence_steps": [1]}), ("isolate_sources", {"reason": "x", "steps": [1]}),
             ("measure_voltage", {"point_a": "TS:A"}), ("wait", {"seconds": "30"}), ("read_panel", {}),
             ("submit_diagnosis", {"outcome": "diagnosed", "confidence": 0.9, "evidence": [{"step": 1, "type": "x", "observation": "o"}]}),
             ("perform_action", {"action": "bypass_interlock", "target": "TS", "reason": "r"})]
    for name, args in calls:
        ours = schema_errors(PARAMS[name], args, name) == []
        theirs = jsonschema.Draft202012Validator(PARAMS[name]).is_valid(args)
        assert ours == theirs, (name, args)
    for spec in TOOL_SPECS:
        jsonschema.Draft202012Validator.check_schema(spec["function"]["parameters"])


@pytest.mark.parametrize("folder", ["20261031_012952_ats_agent_chat_low", "20261031_123544_ats_holdout/agent"])
def test_recorded_agent_calls_fit_the_schema_apart_from_the_isolation_evidence_d47_adds(folder):
    """Every tool call the agent made in the recorded runs fits today's schema, with one exception: isolate_sources had
    no evidence_steps field before D47, and the agent then sent it as a JSON string ("[1, 2, 4]"); all of those were
    refused (none executed), and with the field in the schema they are rejected instead. Where the field was in the
    schema (restore_sources, repeat_transfer_attempt) the agent always sent a list."""
    n = old_isolation = 0
    for f in sorted((ROOT / "results" / "runs" / folder).glob("*.json")):
        tr = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(tr, dict):
            continue
        for e in tr.get("log") or tr.get("tool_log") or []:
            if e["tool"] not in PARAMS:
                continue
            n += 1
            errors = schema_errors(PARAMS[e["tool"]], e["args"], e["tool"])
            if e["tool"] == "isolate_sources" and isinstance(e["args"].get("evidence_steps"), str):
                assert errors == ["isolate_sources.evidence_steps must be array"] and not e["executed"]
                old_isolation += 1
            else:
                assert errors == [], (f.name, e["step"])
    assert n > 100 and old_isolation > 0
