"""Welded / stuck-closed power contacts: what really happens in the power circuit.

A bolted phase-to-phase short needs contacts that tie two supply phases together
directly; then a power fuse must blow. A welded pole that only reaches a winding
end changes the winding connection but every phase-to-phase path still goes
through a winding: no short, the motor runs with unbalanced currents.
"""

import pytest

from probeforge.faults import Fault
from probeforge.sim import Circuit


def started(netlist, fault, button="Start Fwd", wait=0.0):
    c = Circuit(netlist)
    c.apply_fault(fault)
    c.set_power(True)
    c.press(button)
    c.step(wait)
    return c


def test_healthy_currents(netlist):
    c = started(netlist, Fault("HL2", "open", "X1-X2"))  # a lamp fault does not touch the motor
    assert c.indicators()["line_currents_a"] == {"U": 3.3, "V": 3.3, "W": 3.3}
    c.step(6)
    assert c.indicators()["line_currents_a"] == {"U": 10.0, "V": 10.0, "W": 10.0}


@pytest.mark.parametrize("fault, button", [
    (Fault("KM1", "stuck_closed", "1-2"), "Start Rev"),
    (Fault("KM1", "stuck_closed", "5-6"), "Start Rev"),
    (Fault("KM2", "stuck_closed", "1-2"), "Start Fwd"),
    (Fault("KM2", "stuck_closed", "5-6"), "Start Fwd"),
])
def test_crossed_phases_blow_a_power_fuse(netlist, fault, button):
    """A welded KM1/KM2 L1 or L3 pole plus the other direction ties L1 to L3: bolted short."""
    c = started(netlist, fault, button)
    assert any(p.startswith("FU2:") for p in c.blown)
    assert c.events
    ind = c.indicators()
    assert ind["motor"] == "humming"  # what is left is single phase
    assert "overcurrent" in ind["phase_currents"].values()


@pytest.mark.parametrize("fault", [Fault("KM1", "stuck_closed", "3-4"), Fault("KM2", "stuck_closed", "3-4")])
def test_welded_middle_pole_is_harmless(netlist, fault):
    """L2 goes to T2 in both directions, so a welded middle pole changes nothing."""
    for button in ("Start Fwd", "Start Rev"):
        c = started(netlist, fault, button, wait=6)
        assert c.indicators()["motor"].startswith("delta_") and not c.blown


@pytest.mark.parametrize("pole", ["1-2", "3-4", "5-6"])
def test_welded_star_pole_is_latent(netlist, pole):
    """One welded KM3 pole joins a single winding end to the star bridge: nothing else is on it."""
    c = started(netlist, Fault("KM3", "stuck_closed", pole), wait=6)
    assert c.indicators()["motor"] == "delta_forward"
    assert c.indicators()["line_currents_a"] == {"U": 10.0, "V": 10.0, "W": 10.0}


@pytest.mark.parametrize("pole, high", [("1-2", "U"), ("3-4", "V"), ("5-6", "W")])
def test_welded_delta_pole_unbalances_the_star_start(netlist, pole, high):
    """h30: a welded KM4 pole ties one line to the star point while KM3 is closed. One winding is
    bypassed, the other two get 400 V, the tied line carries sqrt(3) x their current. No short,
    the field stays balanced (sequence analysis), so the motor runs in star, unbalanced."""
    c = started(netlist, Fault("KM4", "stuck_closed", pole))
    ind = c.indicators()
    assert ind["motor"] == "star_forward" and not c.blown
    amps = ind["line_currents_a"]
    assert amps[high] == 10.0
    assert all(a == 5.8 for k, a in amps.items() if k != high)
    c.step(6)
    assert c.indicators()["motor"] == "delta_forward"
    assert c.indicators()["line_currents_a"] == {"U": 10.0, "V": 10.0, "W": 10.0}


def test_welded_contactors(netlist):
    c = Circuit(netlist)
    c.apply_fault(Fault("KM1", "welded"))
    c.set_power(True)
    assert c.indicators()["motor"] == "star_forward"  # runs as soon as power is on
    c.press("Start Rev")
    assert c.indicators()["motor"] == "star_forward" and not c.closed["KM2"]  # interlock

    c = started(netlist, Fault("KM4", "welded"))
    assert c.indicators()["motor"] == "delta_forward"  # no star stage, KM3 blocked by interlock
    assert not c.closed["KM3"] and not c.blown


def test_no_single_power_contact_fault_reports_stopped_while_energized(netlist):
    """The old motor model reported 'stopped, zero current' for non-standard winding connections."""
    from probeforge.faults.catalog import all_faults

    for f in all_faults(netlist):
        if f.part is None or netlist.parts[f"{f.component}:{f.part}"].kind != "main":
            continue
        for button in ("Start Fwd", "Start Rev"):
            c = started(netlist, f, button)
            ind = c.indicators()
            energized = any(a > 0 for a in ind["line_currents_a"].values())
            assert (ind["motor"] == "stopped") == (not energized), f"{f} {button}: {ind}"


def test_phase_loss_draws_locked_rotor_current(netlist):
    c = started(netlist, Fault("FU2", "open", "5-6"))
    amps = c.indicators()["line_currents_a"]
    assert amps["W"] == 0.0 and amps["U"] > 1.15 * 10
