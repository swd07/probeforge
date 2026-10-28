import pytest

from probeforge.baseline import HalfSplitBaseline
from probeforge.eval.scoring import score
from probeforge.faults import Fault
from probeforge.faults.catalog import all_faults, has_visible_symptom, load_scenarios
from probeforge.sim import Circuit


def run(netlist, fault):
    c = Circuit(netlist)
    c.apply_fault(fault)
    c.set_power(True)
    b = HalfSplitBaseline(c)
    return b.run(), b


@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s.id)
def test_baseline_solves_hand_written_scenarios(netlist, scenario):
    diagnosis, b = run(netlist, scenario.fault)
    assert score(diagnosis, scenario.fault) == {"component_ok": True, "mode_ok": True, "part_ok": True}
    assert b.tb.policy.stats.blocked == 0


def test_baseline_half_split_is_logarithmic(netlist):
    # s02: stop contact on a 6-net path, found with a handful of probes
    _, b = run(netlist, Fault("SB1", "stuck_open", "11-12"))
    assert b.tb.measurements <= 4


def test_latent_faults_give_insufficient_information(netlist):
    latent = [f for f in all_faults(netlist) if not has_visible_symptom(netlist, f)]
    for f in latent:
        diagnosis, b = run(netlist, f)
        assert diagnosis["outcome"] == "insufficient_information"
        assert b.tb.measurements == 0


def test_baseline_never_crashes_or_violates_policy(netlist):
    for f in all_faults(netlist):
        diagnosis, b = run(netlist, f)
        assert diagnosis is not None
        assert b.tb.policy.stats.blocked == 0
        assert b.tb.policy.stats.approval_requests == 0


def test_baseline_is_deterministic(netlist):
    f = Fault("KT", "stuck")
    a, ba = run(netlist, f)
    b, bb = run(netlist, f)
    assert a == b and [e["args"] for e in ba.tb.log] == [e["args"] for e in bb.tb.log]


def test_observational_twins():
    from probeforge.eval.ambiguity import justified, observational_twins
    from tests.conftest import CIRCUIT_YAML

    welded_button = Fault("SB2", "stuck_closed", "13-14")
    twins = observational_twins(str(CIRCUIT_YAML), welded_button)
    assert twins == [Fault("KM1", "stuck_closed", "13-14")]
    assert observational_twins(str(CIRCUIT_YAML), Fault("FU1", "open", "1-2")) == []
    assert justified({"outcome": "insufficient_information"}, welded_button, twins, correct=False)
    twin = {"outcome": "diagnosed", "component": "KM1", "part": "13-14", "failure_mode": "stuck_closed"}
    assert justified(twin, welded_button, twins, False)
    # pole level: the twin must be named with its part
    assert not justified({**twin, "part": "43-44"}, welded_button, twins, False)
    assert not justified({**twin, "part": ""}, welded_button, twins, False)
    assert not justified({"outcome": "diagnosed", "component": "KM2", "failure_mode": "stuck_closed"}, welded_button, twins, False)
