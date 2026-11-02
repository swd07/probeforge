"""The ATS Engineer panel's arguments (web/src/engineerTools.json, read by web/src/manualArgs.ts) against the frozen
tool schema: since D47 any argument outside a tool's schema fails the step, which once broke the manual operation
check in Engineer mode (it was sent with the cited readings)."""

import json
from pathlib import Path

from probeforge.ats.tools import PARAMS, AtsToolBox, schema_errors
from probeforge.server.ats_common import MANUAL_TOOLS, _f, _outage, CASES, PUBLIC_IDS

CONTRACT = json.loads((Path(__file__).resolve().parents[1] / "web" / "src" / "engineerTools.json").read_text(encoding="utf-8"))
TOOLS = CONTRACT["tools"]

# a value of the right shape for every argument the panel builds
SAMPLE = {
    "seconds": 30, "point_a": "TS:8", "point_b": "TS:9", "reason": "why", "evidence_steps": [1],
    "readings": [{"point_a": "TS:8", "point_b": "TS:9"}], "measure_during": [{"point_a": "TS:A", "point_b": "TS:B"}],
    "action": "adjust_cutoff_contact", "target": "TS:8-9",
    "outcome": "diagnosed", "component": "TS", "part": "8-9", "failure_mode": "stuck_closed", "confidence": 0.8,
    "evidence": [{"step": 1, "type": "instrument_reading", "observation": "0 ohm"}],
}


def test_the_list_covers_every_engineer_tool():
    assert set(TOOLS) == MANUAL_TOOLS


def test_every_argument_set_passes_the_frozen_schema():
    for tool, keys in TOOLS.items():
        args = {k: SAMPLE[k] for k in keys}
        assert schema_errors(PARAMS[tool], args, tool) == [], tool


def test_insufficient_information_passes_too():
    args = {k: SAMPLE[k] for k in ("outcome", "confidence", "evidence")} | {"outcome": "insufficient_information"}
    assert schema_errors(PARAMS["submit_diagnosis"], args, "submit_diagnosis") == []


def test_the_manual_check_runs_with_the_panel_arguments():
    case = CASES[PUBLIC_IDS["dev-07"]]
    tb = AtsToolBox(_outage([_f(d) for d in case["faults"]]), approver=lambda req: True)
    tb.call("isolate_sources", {k: SAMPLE[k] for k in TOOLS["isolate_sources"]})
    result = tb.call("manual_operation_check", {k: SAMPLE[k] for k in TOOLS["manual_operation_check"]})
    assert tb.log[-1]["executed"], result
    assert result["readings_at_other_position"][0]["ohms"] == 0.0
    # the arguments the panel sent before the fix are refused by the schema
    tb.call("manual_operation_check", {**{k: SAMPLE[k] for k in TOOLS["manual_operation_check"]}, "evidence_steps": [1]})
    assert not tb.log[-1]["executed"]
