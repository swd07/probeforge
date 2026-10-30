"""ATS bench simulator (stage S1): the healthy outage timeline against the Group G User's Guide, the symptom of every
dev scenario, the root-cause behaviour (coil burnout chain, jammed mechanism) and the twin check between the
scenario families A (operator circuit) and B (emergency sensing)."""

from pathlib import Path

import pytest
import yaml

from probeforge.ats import ASSUMPTIONS, SETTINGS, AtsBench
from probeforge.ats.ambiguity import twins
from probeforge.ats.faults import all_faults, validate
from probeforge.faults.model import Fault

ROOT = Path(__file__).resolve().parents[1]
CASES = {d["id"]: d for d in (yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "scenarios" / "ats").glob("*.yaml")))}


def faults_of(case: dict) -> list[Fault]:
    raw = case.get("faults") or [case["fault"]]
    return [Fault(f["component"], f["mode"], f.get("part")) for f in raw]


def event_times(b: AtsBench) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in b.indicators()["events"]:
        out.setdefault(e["event"], e["t"])
    return out


def lit(b: AtsBench) -> set[str]:
    return {k for k, v in b.indicators()["lights"].items() if v}


def test_healthy_outage_and_retransfer_follow_the_guide():
    b = AtsBench()
    assert lit(b) == {"Normal accepted", "Load on Normal"} and b.ctl.se and b.ctl.nr and not b.ctl.er
    assert b.coil_voltage() == 0.0  # TS on Normal: cut-off contacts 6-7 / 69-70 open
    b.lose_utility()
    b.step(1.0)  # Feature 1C running, SE already dropped out (guide page 29)
    assert b.ctl.display == "Normal Fail Timer" and not b.ctl.se and b.ctl.nr and "Normal accepted" in lit(b)
    b.step(2.5)
    ev = event_times(b)
    assert ev["N Source Not Accepted"] == pytest.approx(SETTINGS["t_1c"], abs=0.06)  # after 1C (3 s)
    assert ev["Engine Start"] == ev["N Source Not Accepted"] and not b.ctl.nr  # NR drops out: engine start signal
    assert b.ctl.display == "Waiting for Emergency Acceptable" and "Normal accepted" not in lit(b)
    b.step(20.0)
    ev = event_times(b)
    # emergency accepted at 90 % pickup: 3 s (1C) + 2 s cranking + 0.9 x 8 s run-up (assumed start curve)
    expected_accept = SETTINGS["t_1c"] + ASSUMPTIONS["gen_crank_s"] + 0.9 * (ASSUMPTIONS["gen_rated_s"] - ASSUMPTIONS["gen_crank_s"])
    assert ev["E Source Accepted"] == pytest.approx(expected_accept, abs=0.11)
    # Feature 2B is 0: ER right away, then the TS coil operates and the switch reaches Emergency within the travel time
    assert 0 <= ev["Transfer N to E"] - ev["E Source Accepted"] <= ASSUMPTIONS["travel_s"] + 0.2
    assert b.ctl.er and not b.ctl.se and b.position == "E"
    assert lit(b) == {"Emergency accepted", "Load on Emergency"} and b.ctl.display == "Load on Emergency"
    assert b.coil_voltage() == 0.0  # cut-off contacts 8-9 / 71-72 opened at top dead center: coil off, ER stays on
    i = b.indicators()
    assert i["load_powered"] and not i["ups"]["draining"]
    assert i["ups"]["left_s"] == pytest.approx(ASSUMPTIONS["ups_autonomy_s"] - ev["Transfer N to E"], abs=0.2)

    b.restore_utility()
    b.step(1.0)
    assert "N Source Accepted" in event_times(b) and b.ctl.display == "Emergency to Normal Timer"  # Feature 3A
    b.step(SETTINGS["t_3a"] - 5)
    assert b.position == "E" and b.ctl.er
    b.step(10)
    ev = event_times(b)
    assert ev["Transfer E to N"] - ev["N Source Accepted"] == pytest.approx(SETTINGS["t_3a"], abs=0.3)
    assert b.ctl.se and not b.ctl.er and b.position == "N" and b.ctl.display == "Engine Cooldown Timer"
    assert not b.ctl.nr and b.generator_state() == "running"  # cooldown: engine keeps running unloaded (2E)
    b.step(SETTINGS["t_2e"] + 5)
    ev = event_times(b)
    assert ev["Engine Stop"] - ev["Transfer E to N"] == pytest.approx(SETTINGS["t_2e"], abs=1.1)
    assert b.ctl.nr and b.generator_state() == "stopped" and lit(b) == {"Normal accepted", "Load on Normal"}
    assert [e["event"] for e in b.indicators()["events"]] == [
        "N Source Not Accepted", "Engine Start", "E Source Accepted", "Transfer N to E",
        "N Source Accepted", "Transfer E to N", "Engine Stop", "E Source Not Accepted"]


def outage(case: dict, seconds: float = 60.0) -> AtsBench:
    b = AtsBench(faults=faults_of(case))
    b.lose_utility()
    b.step(seconds)
    return b


@pytest.mark.parametrize("cid", sorted(CASES))
def test_every_dev_scenario_shows_its_symptom(cid):
    case = CASES[cid]
    b = outage(case)
    i = b.indicators()
    events = {e["event"] for e in i["events"]}
    fam = case["family"]
    if fam in ("A", "B", "position"):
        assert i["generator"] == "running"
    if fam == "A":  # emergency accepted, ER commanded, the TS does not operate
        assert lit(b) >= {"Emergency accepted", "Alert"} and "Load on Emergency" not in lit(b)
        assert b.ctl.er and b.position == "N" and "Transfer Failure" in events and i["display"] == "Transfer Failure"
        assert not i["load_powered"] and i["ups"]["draining"]
    elif fam == "B":  # generator running but not accepted: no transfer command
        assert "Emergency accepted" not in lit(b) and not b.ctl.er and b.position == "N"
        assert i["display"] == "Waiting for Emergency Acceptable" and "E Source Accepted" not in events
        assert not i["load_powered"] and i["ups"]["draining"]
    elif fam == "position":  # the switch transfers, the controller cannot confirm the position (assumed Position Error)
        assert b.position == "E" and i["load_powered"] and not i["ups"]["draining"]
        assert "Position Error" in events and "Alert" in lit(b) and "Load on Emergency" not in lit(b)
    elif fam == "engine":  # engine start circuit open: the generator never starts
        assert i["generator"] == "stopped" and i["display"] == "Waiting for Emergency Acceptable"
        assert not i["load_powered"] and i["ups"]["draining"]


def test_the_same_first_symptom_for_a_and_b():
    for cid, case in CASES.items():
        if case["family"] in ("A", "B"):
            i = outage(case).indicators()
            assert (i["generator"], i["load_powered"], i["ups"]["draining"]) == ("running", False, True), cid


def test_coil_burnout_chain_and_jammed_mechanism_are_root_causes():
    # cut-off contacts 8-9 and 71-72 not opening at top dead center: the transfer works, the coil stays energized
    # with ER on and burns open (assumed burnout time); a new coil would burn again until the cut-off is fixed
    b = AtsBench(faults=[Fault("TS", "stuck_closed", "8-9"), Fault("TS", "stuck_closed", "71-72")])
    b.lose_utility()
    b.step(20)
    assert b.position == "E" and b.coil_energized() and not b.coil_burnt
    b.step(ASSUMPTIONS["coil_burnout_s"])
    assert b.coil_burnt and b.position == "E" and b.indicators()["load_powered"]
    healthy = AtsBench()
    healthy.lose_utility()
    healthy.step(20 + ASSUMPTIONS["coil_burnout_s"])
    assert not healthy.coil_burnt and not healthy.coil_energized()
    # the chain as found at 03:00: the coil is already burnt, so the next transfer fails (family A symptom)
    chain = outage(CASES["a7_burnout_chain"])
    assert "Transfer Failure" in {e["event"] for e in chain.indicators()["events"]}
    # jammed mechanism: the coil is energized, nothing moves, a repeat command does not help, the coil burns
    j = AtsBench(faults=[Fault("TS", "jammed")])
    j.lose_utility()
    j.step(16)
    assert j.ctl.er and j.coil_energized() and j.position == "N"
    j.step(ASSUMPTIONS["coil_burnout_s"] + 5)
    assert j.coil_burnt and j.position == "N"


def test_scenario_a_and_b_can_be_told_apart_in_simulation():
    cases = {cid: faults_of(c) for cid, c in CASES.items()}
    groups = twins(cases)
    fam = {cid: CASES[cid]["family"] for cid in CASES}
    for g in groups:  # no twins across the families
        assert len({fam[c] for c in g}) == 1, g
    # no twins at all in the dev set; coil open, jammed mechanism and the burnout chain look the same electrically
    # once the coil has burnt, and are told apart by the isolated manual operation check
    assert groups == [], groups
    electrical_only = {}
    for cid in ("a1_coil_open", "a5_jammed", "a7_burnout_chain"):
        from probeforge.ats.ambiguity import signature
        electrical_only[cid] = signature(cases[cid])[:3]
    assert len(set(electrical_only.values())) == 1


def test_fault_catalog_and_validation():
    faults = all_faults(AtsBench().n)
    assert Fault("TS", "jammed") in faults and Fault("H1", "open", "W2_TSA-W2_P2") in faults
    assert Fault("TS", "burnt", "A-B") in faults and Fault("ER", "stuck_open", "J1-X1") in faults
    for case in CASES.values():
        for f in faults_of(case):
            validate(AtsBench().n, f)
    with pytest.raises(ValueError):
        validate(AtsBench().n, Fault("52U", "open", "1-2"))  # 52U stays closed (decision D23)
