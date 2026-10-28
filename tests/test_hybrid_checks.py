"""Scoring at pole level, the correction acceptance rule, the wiring check of flagged regions, and the
mechanical interlock symbol in the drawing."""

import copy
import xml.etree.ElementTree as ET

from probeforge.baseline.infogain import InfoGainBaseline
from probeforge.eval.scoring import grade, parse_fault
from probeforge.faults import Fault
from probeforge.hybrid import run_hybrid
from probeforge.hybrid.acceptance import healthy_changes
from probeforge.hybrid.netlist_io import to_netlist
from probeforge.sim.schematic import render_svg
from tests.test_hybrid import FakeClient, faulty, true_data

KM3_POLE = Fault("KM3", "stuck_open", "1-2")
STAR_PINS = ["KM3:1", "KM3:3", "KM3:5"]


def test_grade_is_pole_level():
    f = parse_fault("KM3:1-2 stuck_open")
    right = {"outcome": "diagnosed", "component": "KM3", "part": "2-1", "failure_mode": "stuck_open"}
    g = grade(right, f, latent=False)
    assert g["correct"] and g["correct_component"] and not g["confident_wrong"]
    g = grade({**right, "part": "3-4"}, f, latent=False)
    assert not g["correct"] and g["correct_component"] and g["confident_wrong"] and not g["pole_open"]
    g = grade({**right, "part": ""}, f, latent=False)
    assert not g["correct"] and g["correct_component"] and g["pole_open"] and not g["confident_wrong"]
    assert grade({"outcome": "insufficient_information"}, f, latent=True)["correct"]
    assert grade({"outcome": "diagnosed", "component": "FU1", "part": "", "failure_mode": "blown"},
                 parse_fault("FU1 blown"), latent=False)["correct"]


def _history_ctx(netlist, fault):
    p = InfoGainBaseline(faulty(netlist, fault), model=netlist)
    p.run()
    return {"netlist": netlist, "history": p.history, "assignments": p.assignments, "power0": True, "amps": p.amps}


def test_acceptance_keeps_unchanged_behaviour_and_rejects_a_supply_tie(netlist):
    ctx = _history_ctx(netlist, Fault("SB2", "stuck_open", "13-14"))
    assert healthy_changes(ctx, netlist) == []
    tied = true_data()
    nets = tied["nets"]
    src = next(k for k, v in nets.items() if "KM1:5" in v)
    dst = next(k for k, v in nets.items() if "KM1:1" in v)
    nets[src] = [t for t in nets[src] if t != "KM1:5"]
    nets[dst] = [*nets[dst], "KM1:5"]
    reasons = healthy_changes(ctx, to_netlist(tied))
    assert reasons and all("contradicted" in r or "matched" in r for r in reasons)


def _swapped_star(data: dict) -> dict:
    """The true netlist with the KM3 star-side pins 1 and 3 read in each other's nets (a crossover misread)."""
    d = copy.deepcopy(data)
    for net, terms in d["nets"].items():
        d["nets"][net] = ["KM3:3" if t == "KM3:1" else "KM3:1" if t == "KM3:3" else t for t in terms]
    return d


def test_wiring_check_drops_a_pole_that_depends_on_a_flagged_region(netlist):
    model = _swapped_star(true_data())
    plain = run_hybrid(faulty(netlist, KM3_POLE), FakeClient(None), model, b"png", do_explain=False, flags=[])
    assert plain.diagnosis["component"] == "KM3" and plain.diagnosis["part"] == "3-4"  # confidently wrong pole
    flags = [{"terminals": STAR_PINS, "reason": "star wiring crosses"}]
    r = run_hybrid(faulty(netlist, KM3_POLE), FakeClient(None), model, b"png", do_explain=False, flags=flags)
    d = r.diagnosis
    assert d["component"] == "KM3" and d["part"] == "" and d["confidence"] < 1 and "pole ambiguous" in d["note"]
    assert r.wiring_check["verdict"] == "pole ambiguous" and r.wiring_check["consistent_alternatives"] >= 1

    asked = []

    def human(request):
        asked.append(request)
        return next(i for i, o in enumerate(request["options"]) if o["fault"] == str(KM3_POLE))

    r = run_hybrid(faulty(netlist, KM3_POLE), FakeClient(None), model, b"png", do_explain=False, flags=flags,
                   confirm_wiring=human)
    assert asked and asked[0]["region"] == STAR_PINS
    assert (r.diagnosis["part"], r.diagnosis["confidence"]) == ("1-2", 1.0)


def test_drawing_shows_mechanical_interlocks(netlist):
    root = ET.fromstring(render_svg(netlist))
    marks = [p for p in root.iter("{http://www.w3.org/2000/svg}polygon") if "interlock" in (p.get("class") or "")]
    assert len(marks) == len(netlist.interlocks) == 2
