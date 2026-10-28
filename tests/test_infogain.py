import pytest

from probeforge.baseline import InfoGainBaseline
from probeforge.eval.scoring import score
from probeforge.faults import Fault
from probeforge.faults.catalog import load_scenarios
from probeforge.sim import Circuit


def run(netlist, fault):
    c = Circuit(netlist)
    c.apply_fault(fault)
    c.set_power(True)
    b = InfoGainBaseline(c)
    return b.run(), b


@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s.id)
def test_solves_scenarios_within_policy(netlist, scenario):
    d, b = run(netlist, scenario.fault)
    s = score(d, scenario.fault)
    assert s["component_ok"] and s["mode_ok"]
    assert b.tb.policy.stats.blocked == 0 and b.tb.policy.stats.approval_requests == 0
    assert b.tb.measurements <= 6


def test_observational_twins_stay_ambiguous(netlist):
    d, b = run(netlist, Fault("SB2", "stuck_closed", "13-14"))
    assert d["outcome"] == "insufficient_information"  # KM1 13-14 welded reads the same everywhere
    assert set(b.faults_left) == {Fault("SB2", "stuck_closed", "13-14"), Fault("KM1", "stuck_closed", "13-14")}


def test_clone_is_independent(netlist):
    c = Circuit(netlist)
    c.set_power(True)
    k = c.clone()
    k.press("Start Fwd")
    assert k.indicators()["motor"] == "star_forward" and c.indicators()["motor"] == "stopped"
    assert not c.closed["KM1"]
