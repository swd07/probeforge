"""Each scenario fault produces exactly the external symptom from the CLAUDE.md table."""

import random

import pytest

from probeforge.faults import Fault
from probeforge.faults.catalog import (
    all_faults,
    has_visible_symptom,
    load_scenarios,
    operator_observation,
    random_fault,
)
from probeforge.sim import Circuit

SCENARIOS = {s.id: s for s in load_scenarios()}
ALL_LAMPS_OFF = {"Power": False, "Fault": False, "Forward": False, "Reverse": False}
IDLE = {"Power": True, "Fault": False, "Forward": False, "Reverse": False}


def faulty(netlist, sid: str) -> Circuit:
    c = Circuit(netlist)
    c.apply_fault(SCENARIOS[sid].fault)
    c.set_power(True)
    return c


def ind(c):
    return c.indicators()


def test_eight_scenarios_present():
    assert sorted(SCENARIOS) == [f"s0{i}" for i in range(1, 9)]
    for s in SCENARIOS.values():
        assert s.circuit.exists()
        assert s.symptom


def test_s01_control_fuse_blown(netlist):
    """Nothing responds, Power lamp off."""
    c = faulty(netlist, "s01")
    assert ind(c)["lamps"] == ALL_LAMPS_OFF
    for button in ("Start Fwd", "Start Rev"):
        c.press(button)
        c.step(1)
        assert ind(c)["lamps"] == ALL_LAMPS_OFF
        assert ind(c)["motor"] == "stopped"


def test_s02_stop_stuck_open(netlist):
    """Nothing responds, Power lamp on."""
    c = faulty(netlist, "s02")
    assert ind(c)["lamps"] == IDLE
    for button in ("Start Fwd", "Start Rev"):
        c.press(button)
        c.step(1)
        assert ind(c)["lamps"] == IDLE
        assert ind(c)["motor"] == "stopped"


def test_s03_thermal_tripped(netlist):
    """Fault lamp on, no start."""
    c = faulty(netlist, "s03")
    assert ind(c)["lamps"] == {"Power": True, "Fault": True, "Forward": False, "Reverse": False}
    for button in ("Start Fwd", "Start Rev"):
        c.press(button)
        c.step(1)
        assert ind(c)["motor"] == "stopped"
        assert ind(c)["lamps"]["Fault"]


def test_s04_forward_coil_open(netlist):
    """Forward does not start, reverse works."""
    c = faulty(netlist, "s04")
    c.press("Start Fwd")
    c.step(1)
    assert ind(c)["motor"] == "stopped"
    assert ind(c)["lamps"] == IDLE
    c.press("Start Rev")
    assert ind(c)["motor"] == "star_reverse"
    c.step(6)
    assert ind(c)["motor"] == "delta_reverse"


def test_s05_self_hold_not_closing(netlist):
    """Motor runs only while Start is held."""
    c = faulty(netlist, "s05")
    c.press("Start Fwd")
    assert ind(c)["motor"] == "stopped"
    c.hold("Start Fwd")
    assert ind(c)["motor"] == "star_forward"
    c.step(6)
    assert ind(c)["motor"] == "delta_forward"
    c.release("Start Fwd")
    assert ind(c)["motor"] == "stopped"
    # reverse self-hold is a different contact and still works
    c.press("Start Rev")
    assert ind(c)["motor"] == "star_reverse"


@pytest.mark.parametrize("sid", ["s06", "s07"])
def test_s06_s07_motor_stays_in_star(netlist, sid):
    """Motor stays in star (s06 timer failed, s07 star contactor welded)."""
    c = faulty(netlist, sid)
    c.press("Start Fwd")
    assert ind(c)["motor"] == "star_forward"
    c.step(15)
    assert ind(c)["motor"] == "star_forward"
    assert ind(c)["lamps"] == {"Power": True, "Fault": False, "Forward": True, "Reverse": False}
    assert not c.closed["KM4"]


def test_s07_interlock_blocks_delta(netlist):
    """Timer has switched, but the welded KM3 keeps its 21-22 open so KM4 gets no voltage."""
    c = faulty(netlist, "s07")
    c.press("Start Fwd")
    c.step(6)
    assert c.voltage("KT:67", "KT:68") == 0.0  # timer contact closed
    assert c.voltage("KM3:21", "KM3:22") == 230.0  # interlock contact open
    assert c.voltage("KM4:A1", "KM4:A2") == 0.0


def test_s08_phase_loss(netlist):
    """Motor hums, thermal relay trips."""
    c = faulty(netlist, "s08")
    c.press("Start Fwd")
    assert ind(c)["motor"] == "humming"
    assert ind(c)["phase_currents"] == {"U": "overcurrent", "V": "overcurrent", "W": "zero"}
    assert not ind(c)["lamps"]["Fault"]
    c.step(10)
    assert ind(c)["motor"] == "stopped"
    assert ind(c)["lamps"]["Fault"]
    assert c.tripped["KK1"]


# Similar-symptom pairs must still be separable by a measurement.

def test_pair_s01_s02_separable_by_voltage(netlist):
    assert faulty(netlist, "s01").voltage("FU1:2", "N") == 0.0
    assert faulty(netlist, "s02").voltage("FU1:2", "N") == 230.0


def test_pair_s04_s05_separable_by_coil_resistance(netlist):
    assert faulty(netlist, "s04").resistance("KM1:A1", "KM1:A2") != 550.0
    c5 = faulty(netlist, "s05")
    c5.set_power(False)
    assert c5.resistance("KM1:A1", "KM1:A2") == 550.0


def test_pair_s06_s07_separable_by_star_coil_voltage(netlist):
    readings = {}
    for sid in ("s06", "s07"):
        c = faulty(netlist, sid)
        c.press("Start Fwd")
        c.step(6)
        readings[sid] = c.voltage("KM3:A1", "KM3:A2")
    # s06: timer never switched so KM3 coil is still fed; s07: coil dropped but contactor stays in
    assert readings == {"s06": 230.0, "s07": 0.0}


# Random fault generator

def test_all_faults_apply_and_simulate(netlist):
    faults = all_faults(netlist)
    assert len(faults) > 80
    assert len(set(faults)) == len(faults)
    for f in faults:
        c = Circuit(netlist)
        c.apply_fault(f)
        operator_observation(c)  # must not raise or chatter


def test_scenario_faults_are_in_catalog(netlist):
    catalog = set(all_faults(netlist))
    for s in SCENARIOS.values():
        assert s.fault in catalog
        assert has_visible_symptom(netlist, s.fault)


def test_random_fault_repeatable(netlist):
    assert random_fault(netlist, 42) == random_fault(netlist, 42)
    rng = random.Random(7)
    picks = {random_fault(netlist, rng) for _ in range(50)}
    assert len(picks) > 20


def test_random_fault_visible_only(netlist):
    for seed in range(5):
        assert has_visible_symptom(netlist, random_fault(netlist, seed, visible_only=True))


def test_invalid_faults_rejected(circuit):
    with pytest.raises(ValueError):
        circuit.apply_fault(Fault("KM9", "open"))
    with pytest.raises(ValueError):
        circuit.apply_fault(Fault("KM1", "open", "99-98"))
    with pytest.raises(ValueError):
        circuit.apply_fault(Fault("FU1", "welded", "1-2"))
    with pytest.raises(ValueError):
        circuit.apply_fault(Fault("SB1", "welded"))
