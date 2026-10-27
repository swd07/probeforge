"""Healthy circuit behaviour and measurement physics."""

import math

import pytest

from probeforge.faults import Fault


def lamps(c):
    return c.indicators()["lamps"]


def motor(c):
    return c.indicators()["motor"]


def test_power_off_everything_dark(circuit):
    assert lamps(circuit) == {"Power": False, "Fault": False, "Forward": False, "Reverse": False}
    assert motor(circuit) == "stopped"


def test_power_on_lights_power_lamp_only(powered):
    assert lamps(powered) == {"Power": True, "Fault": False, "Forward": False, "Reverse": False}
    assert motor(powered) == "stopped"


def test_forward_star_then_delta_then_stop(powered):
    c = powered
    c.press("Start Fwd")
    assert motor(c) == "star_forward"
    assert lamps(c)["Forward"]
    assert c.closed == {"KM1": True, "KM2": False, "KM3": True, "KM4": False}
    assert set(c.indicators()["phase_currents"].values()) == {"nominal"}

    c.step(3)
    assert motor(c) == "star_forward"  # timer (5 s) not elapsed yet
    c.step(3)
    assert motor(c) == "delta_forward"
    assert c.closed == {"KM1": True, "KM2": False, "KM3": False, "KM4": True}

    c.press("Stop")
    assert motor(c) == "stopped"
    assert not lamps(c)["Forward"]
    assert not any(c.closed.values())


def test_reverse_star_then_delta(powered):
    c = powered
    c.press("Start Rev")
    assert motor(c) == "star_reverse"
    assert lamps(c)["Reverse"] and not lamps(c)["Forward"]
    c.step(6)
    assert motor(c) == "delta_reverse"


def test_forward_stop_reverse_sequence(powered):
    c = powered
    c.press("Start Fwd")
    c.step(6)
    c.press("Stop")
    c.press("Start Rev")
    c.step(6)
    assert motor(c) == "delta_reverse"
    c.press("Stop")
    assert motor(c) == "stopped"


def test_self_hold_keeps_running_after_release(powered):
    powered.press("Start Fwd")
    powered.step(1)
    assert motor(powered) == "star_forward"


def test_electrical_interlock_blocks_reverse_while_forward(powered):
    c = powered
    c.press("Start Fwd")
    c.press("Start Rev")
    assert motor(c) == "star_forward"
    assert not c.closed["KM2"]


def test_mechanical_interlock_blocks_reverse_even_if_electrical_one_fails(powered):
    c = powered
    c.apply_fault(Fault("KM1", "stuck_closed", "21-22"))  # KM2 rung interlock contact fails
    c.press("Start Fwd")
    c.hold("Start Rev")
    assert c.closed["KM1"] and not c.closed["KM2"]
    assert motor(c) == "star_forward"
    assert not c.events  # no short circuit, nothing blew


def test_power_off_drops_everything(powered):
    powered.press("Start Fwd")
    powered.set_power(False)
    assert motor(powered) == "stopped"
    assert not any(powered.closed.values())


def test_timer_restarts_after_stop(powered):
    c = powered
    c.press("Start Fwd")
    c.step(3)
    c.press("Stop")
    c.press("Start Fwd")
    c.step(3)
    assert motor(c) == "star_forward"


def test_phase_voltages(powered):
    assert powered.voltage("L1", "N") == 230.0
    assert powered.voltage("L1", "L2") == pytest.approx(398.4, abs=0.1)
    assert powered.voltage("L2", "L3") == pytest.approx(398.4, abs=0.1)


def test_supply_side_of_breaker_stays_live_when_off(circuit):
    assert circuit.voltage("QF1:1", "N") == 230.0
    assert circuit.voltage("QF1:2", "N") == 0.0


def test_voltage_across_open_contact_reads_supply(powered):
    # Start Fwd open: wire 3 is live, wire 4 is pulled to N through the KM1 coil
    assert powered.voltage("SB2:13", "SB2:14") == 230.0
    assert powered.voltage("3", "N") == 230.0
    assert powered.voltage("4", "N") == 0.0
    # closed contact: no voltage across it
    assert powered.voltage("SB1:11", "SB1:12") == 0.0


def test_voltage_accepts_net_names_and_terminals(powered):
    assert powered.voltage("1", "N") == powered.voltage("FU1:2", "HL1:X2")
    with pytest.raises(KeyError):
        powered.voltage("XX:1", "N")


def test_coil_voltage_when_running(powered):
    powered.press("Start Fwd")
    assert powered.voltage("KM1:A1", "KM1:A2") == 230.0
    assert powered.voltage("KM3:A1", "KM3:A2") == 230.0
    assert powered.voltage("KM4:A1", "KM4:A2") == 0.0


def test_resistance_values(circuit):
    assert circuit.resistance("FU1:1", "FU1:2") == 0.0
    assert circuit.resistance("KM1:A1", "KM1:A2") == 550.0
    # KT coil is in parallel with the KM3 coil through the closed KT 55-56 and KM4 21-22
    assert circuit.resistance("KT:A1", "KT:A2") == pytest.approx(1 / (1 / 4000 + 1 / 550), abs=0.1)
    # open contactor main pole: nothing in parallel on the power side
    assert math.isinf(circuit.resistance("KM1:1", "KM1:2"))


def test_resistance_sees_parallel_paths(circuit):
    # Start Fwd open, but wire 3 and wire 4 are joined through the Power lamp and KM1 coil via N
    assert circuit.resistance("SB2:13", "SB2:14") == 2600.0 + 550.0


def test_holding_button_closes_contact_for_continuity(circuit):
    circuit.hold("Start Fwd")
    assert circuit.resistance("SB2:13", "SB2:14") == 0.0


def test_short_circuit_blows_control_fuse(powered):
    powered.apply_fault(Fault("KM1", "short", "A1-A2"))
    assert lamps(powered)["Power"]  # coil not connected to L yet
    powered.press("Start Fwd")
    assert "FU1:1-2" in powered.blown
    assert not lamps(powered)["Power"]
    assert powered.events


def test_deterministic(netlist):
    from probeforge.sim import Circuit

    def run():
        c = Circuit(netlist)
        c.set_power(True)
        c.press("Start Fwd")
        c.step(7)
        return c.indicators(), c.voltage("8", "N"), c.time

    assert run() == run()
