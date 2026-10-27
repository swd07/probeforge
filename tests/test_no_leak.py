"""The agent must never receive the injected fault through any channel.

For every one of the 91 possible faults, drive every tool (as an agent would),
build the initial prompt, and check that no tool output, log entry or prompt
text names the fault or any scenario.
"""

import json

import pytest

from probeforge.agent import loop
from probeforge.faults.catalog import all_faults, load_scenarios
from probeforge.sim import Circuit
from probeforge.tools import ToolBox

SCENARIO_TITLES = [s.title for s in load_scenarios()]


def forbidden_strings(fault) -> list[str]:
    items = [str(fault), f"{fault.component} {fault.mode}", json.dumps(fault.to_dict())]
    if fault.part:
        items += [fault.target, f"{fault.component} {fault.part}"]
    return items + SCENARIO_TITLES


def drive_all_tools(tb: ToolBox, netlist) -> None:
    tb.call("read_indicators", {})
    tb.call("get_schematic", {})
    for button in ("Start Fwd", "Stop", "Start Rev", "Stop"):
        tb.call("press_button", {"button": button, "hold_seconds": 1})
    tb.call("press_button", {"button": "Start Fwd"})
    tb.call("wait", {"seconds": 10})
    for net in netlist.nets:
        tb.call("measure_voltage", {"point_a": net, "point_b": "N"})
    tb.call("measure_voltage", {"point_a": "XX:9", "point_b": "N"})  # error path
    tb.call("set_power", {"on": False})
    for part in netlist.parts.values():
        tb.call("measure_resistance", {"point_a": part.a, "point_b": part.b})
    tb.call("set_power", {"on": True, "reason": "test"})
    tb.call("set_power", {"on": True})
    for action in ("reset_protection", "bypass_interlock", "replace_part"):
        tb.call("perform_action", {"action": action, "target": "KK1", "reason": "test"})
    tb.call("update_hypotheses", {"hypotheses": []})
    tb.call("submit_diagnosis", {"outcome": "insufficient_information", "confidence": 0.1, "evidence": []})


@pytest.fixture
def no_png(monkeypatch):
    # the PNG is rendered from the netlist alone; skip rasterizing it 91 times
    monkeypatch.setattr(loop, "render_png", lambda netlist: b"png")


def test_no_tool_output_log_or_prompt_reveals_fault(netlist, no_png):
    faults = all_faults(netlist)
    assert len(faults) == 91
    for fault in faults:
        c = Circuit(netlist)
        c.apply_fault(fault)
        c.set_power(True)
        tb = ToolBox(c)
        prompt = loop.build_initial_messages(tb)
        drive_all_tools(tb, netlist)
        text_parts = [prompt[0]["content"], prompt[1]["content"][0]["text"], json.dumps(tb.log), json.dumps(tb.hypotheses_history)]
        blob = "\n".join(text_parts)
        for s in forbidden_strings(fault):
            assert s not in blob, f"{fault}: found {s!r}"


def test_prompt_is_identical_for_every_fault(netlist, no_png):
    """Strongest form of the check: the initial prompt does not depend on the fault at all
    beyond the panel state the operator would see."""
    prompts = set()
    for fault in all_faults(netlist):
        c = Circuit(netlist)
        c.apply_fault(fault)
        c.set_power(True)
        msgs = loop.build_initial_messages(ToolBox(c))
        prompts.add((msgs[0]["content"], msgs[1]["content"][0]["text"].split("Step 0")[0]))
    assert len(prompts) == 1


def test_png_depends_only_on_netlist():
    import inspect

    from probeforge.sim.schematic import render_png

    assert list(inspect.signature(render_png).parameters) == ["netlist", "zoom"]


def test_circuit_events_not_exposed(netlist):
    from probeforge.faults import Fault

    c = Circuit(netlist)
    c.apply_fault(Fault("KM1", "short", "A1-A2"))
    c.set_power(True)
    tb = ToolBox(c)
    r = tb.call("press_button", {"button": "Start Fwd"})
    assert c.events  # FU1 blew
    assert "FU1" not in json.dumps(r) and "blew" not in json.dumps(r)
    assert r["note"] == "A protection device operated during this action."
