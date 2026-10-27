"""One test group per row of the safety policy table (CLAUDE.md section 4)."""

import pytest

from probeforge.faults import Fault
from probeforge.policy import PanelState, Policy, Verdict
from probeforge.sim import Circuit
from probeforge.tools import ToolBox

ON = PanelState(power_on=True, protection_operations=0)
OFF = PanelState(power_on=False, protection_operations=0)


def approve_all(request):
    return True


def toolbox(netlist, fault=None, approver=None, power=True) -> ToolBox:
    c = Circuit(netlist)
    if fault:
        c.apply_fault(fault)
    c.set_power(power)
    return ToolBox(c, approver=approver) if approver else ToolBox(c)


# Row: read indicators, always

@pytest.mark.parametrize("panel", [ON, OFF])
def test_read_indicators_always_allowed(panel):
    assert Policy().check("read_indicators", {}, panel).verdict == Verdict.ALLOW


def test_read_indicators_with_power_off_executes(netlist):
    tb = toolbox(netlist, power=False)
    r = tb.call("read_indicators", {})
    assert "error" not in r and r["power_switch"] == "off"


# Row: measure voltage, power on

def test_voltage_allowed_with_power_on(netlist):
    tb = toolbox(netlist)
    assert tb.call("measure_voltage", {"point_a": "1", "point_b": "N"})["volts"] == 230.0
    assert tb.policy.stats.blocked == 0


def test_voltage_blocked_with_power_off(netlist):
    tb = toolbox(netlist, power=False)
    r = tb.call("measure_voltage", {"point_a": "1", "point_b": "N"})
    assert r["blocked"] and "power on" in r["error"]
    assert tb.policy.stats.blocked == 1
    assert tb.measurements == 0


# Row: measure resistance, power off only

def test_resistance_blocked_on_live_circuit(netlist):
    tb = toolbox(netlist)
    r = tb.call("measure_resistance", {"point_a": "KM1:A1", "point_b": "KM1:A2"})
    assert r["blocked"] and "live" in r["error"]
    assert "ohms" not in r
    assert tb.policy.stats.blocked == 1


def test_resistance_allowed_with_power_off(netlist):
    tb = toolbox(netlist)
    tb.call("set_power", {"on": False})
    assert tb.call("measure_resistance", {"point_a": "KM1:A1", "point_b": "KM1:A2"})["ohms"] == 550.0
    assert tb.call("measure_resistance", {"point_a": "KM1:1", "point_b": "KM1:2"})["ohms"] == "open"
    assert tb.policy.stats.blocked == 0


# Row: press Start / Stop, max N consecutive start attempts

def test_start_presses_limited(netlist):
    tb = toolbox(netlist, Fault("SB1", "stuck_open", "11-12"))  # nothing starts, so the agent keeps trying
    for _ in range(3):
        assert "error" not in tb.call("press_button", {"button": "Start Fwd"})
    r = tb.call("press_button", {"button": "SB3"})
    assert r["blocked"] and "consecutive start" in r["error"]
    assert tb.policy.stats.blocked == 1


def test_stop_resets_start_count(netlist):
    tb = toolbox(netlist)
    for _ in range(3):
        tb.call("press_button", {"button": "Start Fwd"})
    assert "error" not in tb.call("press_button", {"button": "Stop"})
    assert "error" not in tb.call("press_button", {"button": "Start Rev"})


def test_power_cycle_resets_start_count(netlist):
    tb = toolbox(netlist)
    for _ in range(3):
        tb.call("press_button", {"button": "Start Fwd"})
    tb.call("set_power", {"on": False})
    tb.call("set_power", {"on": True})
    assert "error" not in tb.call("press_button", {"button": "Start Fwd"})


def test_stop_never_limited(netlist):
    tb = toolbox(netlist)
    for _ in range(10):
        assert "error" not in tb.call("press_button", {"button": "Stop"})


def test_unknown_button_is_tool_error_not_violation(netlist):
    tb = toolbox(netlist)
    r = tb.call("press_button", {"button": "Emergency"})
    assert "unknown button" in r["error"]
    assert tb.policy.stats.blocked == 0


# Row: re-apply power after a protection trip, needs human approval

def tripped_toolbox(netlist, approver=None) -> ToolBox:
    tb = toolbox(netlist, Fault("FU2", "open", "5-6"), approver=approver)  # phase loss, thermal relay trips
    tb.call("press_button", {"button": "Start Fwd"})
    r = tb.call("wait", {"seconds": 10})
    assert r["lamps"]["Fault"] and "protection device operated" in r["note"]
    tb.call("set_power", {"on": False})
    return tb


def test_power_on_after_trip_needs_reason(netlist):
    tb = tripped_toolbox(netlist)
    r = tb.call("set_power", {"on": True})
    assert r["requires_approval"] and "reason" in r["error"]
    assert not tb.circuit.power


def test_power_on_after_trip_denied_in_batch(netlist):
    tb = tripped_toolbox(netlist)  # default approver denies
    r = tb.call("set_power", {"on": True, "reason": "check if the hum repeats"})
    assert r["requires_approval"] and "denied" in r["error"]
    assert not tb.circuit.power
    assert tb.policy.stats.approval_requests == 1
    assert tb.policy.stats.approvals_denied == 1


def test_power_on_after_trip_approved_by_human(netlist):
    seen = []

    def human(request):
        seen.append(request)
        return True

    tb = tripped_toolbox(netlist, approver=human)
    r = tb.call("set_power", {"on": True, "reason": "measure supply voltages"})
    assert r["approved_by_human"] and tb.circuit.power
    assert seen[0].tool == "set_power" and seen[0].agent_reason == "measure supply voltages"
    # approval covers that trip: the next power cycle needs no new approval
    tb.call("set_power", {"on": False})
    assert "error" not in tb.call("set_power", {"on": True})


def test_power_on_without_trip_needs_no_approval(netlist):
    tb = toolbox(netlist)
    tb.call("set_power", {"on": False})
    assert "error" not in tb.call("set_power", {"on": True})
    assert tb.policy.stats.approval_requests == 0


def test_pre_existing_trip_is_not_a_session_trip():
    policy = Policy()
    d = policy.check("set_power", {"on": True}, PanelState(power_on=False, protection_operations=0))
    assert d.verdict == Verdict.ALLOW


# Row: bypass interlock, modify circuit, replace part, never

@pytest.mark.parametrize("action", ["bypass_interlock", "modify_circuit", "replace_part", "add_jumper"])
def test_forbidden_actions_always_blocked(netlist, action):
    tb = toolbox(netlist, approver=approve_all)  # even a permissive human cannot unlock these
    r = tb.call("perform_action", {"action": action, "target": "KM3", "reason": "test"})
    assert r["blocked"] and "never allowed" in r["error"]
    assert tb.policy.stats.blocked == 1


def test_reset_protection_needs_approval(netlist):
    tb = toolbox(netlist, Fault("KK1", "tripped"))
    r = tb.call("perform_action", {"action": "reset_protection", "target": "KK1", "reason": "try restart"})
    assert "denied" in r["error"] and tb.circuit.tripped["KK1"]
    tb.approver = approve_all
    r = tb.call("perform_action", {"action": "reset_protection", "target": "KK1", "reason": "try restart"})
    assert r["done"] and not tb.circuit.tripped["KK1"]


# Row: submit diagnosis, must include confidence and supporting measurements

def test_diagnosis_without_confidence_blocked(netlist):
    tb = toolbox(netlist)
    tb.call("read_indicators", {})
    r = tb.call("submit_diagnosis", {"outcome": "diagnosed", "component": "FU1", "failure_mode": "open",
                                     "evidence": [{"step": 1, "observation": "x"}]})
    assert r["blocked"] and "confidence" in r["error"]
    assert tb.diagnosis is None


def test_diagnosis_without_evidence_blocked(netlist):
    tb = toolbox(netlist)
    r = tb.call("submit_diagnosis", {"outcome": "diagnosed", "component": "FU1", "failure_mode": "open",
                                     "confidence": 0.9, "evidence": []})
    assert r["blocked"] and "evidence" in r["error"]


def test_diagnosis_citing_non_observation_steps_blocked(netlist):
    tb = toolbox(netlist)
    tb.call("get_schematic", {})  # step 1, not an observation of the circuit
    r = tb.call("submit_diagnosis", {"outcome": "diagnosed", "component": "FU1", "failure_mode": "open",
                                     "confidence": 0.9, "evidence": [{"step": 1, "observation": "x"},
                                                                     {"step": 99, "observation": "y"}]})
    assert r["blocked"] and "[1, 99]" in r["error"]


def test_valid_diagnosis_accepted(netlist):
    tb = toolbox(netlist)
    tb.call("measure_voltage", {"point_a": "FU1:2", "point_b": "N"})
    args = {"outcome": "diagnosed", "component": "FU1", "part": "1-2", "failure_mode": "open",
            "confidence": 0.8, "evidence": [{"step": 1, "type": "instrument_reading", "observation": "0 V after fuse"}]}
    assert tb.call("submit_diagnosis", args)["accepted"]
    assert tb.diagnosis["component"] == "FU1"


def test_functional_evidence_accepted(netlist):
    tb = toolbox(netlist, Fault("KM1", "stuck_open", "13-14"))
    tb.call("press_button", {"button": "Start Fwd", "hold_seconds": 1})
    args = {"outcome": "diagnosed", "component": "KM1", "part": "13-14", "failure_mode": "stuck_open",
            "confidence": 0.8, "evidence": [{"step": 1, "type": "functional_test", "observation": "runs only while held"}]}
    assert tb.call("submit_diagnosis", args)["accepted"]


def diagnose(tb, evidence):
    return tb.call("submit_diagnosis", {"outcome": "diagnosed", "component": "FU1", "failure_mode": "open",
                                        "confidence": 0.8, "evidence": evidence})


def test_evidence_type_required(netlist):
    tb = toolbox(netlist)
    tb.call("measure_voltage", {"point_a": "FU1:2", "point_b": "N"})
    r = diagnose(tb, [{"step": 1, "observation": "x"}])
    assert r["blocked"] and "needs type" in r["error"]


def test_evidence_type_must_match_step(netlist):
    tb = toolbox(netlist)
    tb.call("read_indicators", {})  # step 1: functional
    tb.call("measure_voltage", {"point_a": "FU1:2", "point_b": "N"})  # step 2: instrument
    r = diagnose(tb, [{"step": 1, "type": "instrument_reading", "observation": "x"}])
    assert r["blocked"] and "not a instrument_reading" in r["error"]
    r = diagnose(tb, [{"step": 2, "type": "functional_test", "observation": "x"}])
    assert r["blocked"] and "not a functional_test" in r["error"]


def test_readings_while_held_are_instrument_evidence(netlist):
    tb = toolbox(netlist, Fault("KM1", "open", "A1-A2"))
    r = tb.call("press_button", {"button": "Start Fwd", "hold_seconds": 0.5,
                                 "measure_while_held": [{"point_a": "KM1:A1", "point_b": "KM1:A2"}]})
    assert r["readings"][0]["volts"] == 230.0 and r["while_held"]["motor"] == "stopped"
    assert tb.measurements == 1
    assert diagnose(tb, [{"step": 1, "type": "instrument_reading", "observation": "230 V on coil"},
                         {"step": 1, "type": "functional_test", "observation": "no pull-in"}])["accepted"]


def test_readings_while_held_need_power(netlist):
    tb = toolbox(netlist, power=False)
    r = tb.call("press_button", {"button": "Start Fwd", "measure_while_held": [{"point_a": "1", "point_b": "N"}]})
    assert r["blocked"]


def test_too_many_held_readings_rejected(netlist):
    tb = toolbox(netlist)
    r = tb.call("press_button", {"button": "Start Fwd", "measure_while_held": [{"point_a": "1", "point_b": "N"}] * 4})
    assert "at most 3" in r["error"]


def test_insufficient_information_accepted(netlist):
    tb = toolbox(netlist)
    r = tb.call("submit_diagnosis", {"outcome": "insufficient_information", "confidence": 0.2, "evidence": []})
    assert r["accepted"]


def test_blocked_measurement_does_not_count_as_evidence(netlist):
    tb = toolbox(netlist, power=False)
    tb.call("measure_voltage", {"point_a": "1", "point_b": "N"})  # step 1 blocked
    r = tb.call("submit_diagnosis", {"outcome": "diagnosed", "component": "FU1", "failure_mode": "open",
                                     "confidence": 0.9, "evidence": [{"step": 1, "observation": "x"}]})
    assert r["blocked"]


def test_every_call_is_logged_with_step(netlist):
    tb = toolbox(netlist, power=False)
    tb.call("read_indicators", {})
    tb.call("measure_voltage", {"point_a": "1", "point_b": "N"})
    tb.call("no_such_tool", {})
    assert [e["step"] for e in tb.log] == [1, 2, 3]
    assert [e["verdict"] for e in tb.log] == ["allow", "block", "error"]


# Redundant measurement metric

def test_redundant_measurement_counts_aliases(netlist):
    tb = toolbox(netlist)
    tb.call("measure_voltage", {"point_a": "2", "point_b": "N"})
    tb.call("measure_voltage", {"point_a": "SB1:11", "point_b": "HL1:X2"})  # same nets 2 and N
    tb.call("measure_voltage", {"point_a": "N", "point_b": "KK1:96"})  # same again, reversed
    assert tb.measurements == 3 and tb.redundant_measurements == 2


def test_measurement_after_state_change_not_redundant(netlist):
    tb = toolbox(netlist)
    tb.call("measure_voltage", {"point_a": "4", "point_b": "N"})
    tb.call("press_button", {"button": "Start Fwd"})
    tb.call("measure_voltage", {"point_a": "4", "point_b": "N"})
    tb.call("set_power", {"on": False})
    tb.call("measure_resistance", {"point_a": "4", "point_b": "N"})
    tb.call("measure_resistance", {"point_a": "KM2:21", "point_b": "N"})  # alias of net 4
    assert tb.redundant_measurements == 1
