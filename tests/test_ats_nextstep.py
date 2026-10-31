"""The next-step helper for the UI reads the frozen planner from its update hook and changes nothing: a run with the
helper is identical to a run without it, and every plan shown is the step the run takes next (the full 12-case check
over the baseline and the saved transcriptions is scripts/ats_nextstep_identity.py)."""

import json

from probeforge.ats import AtsBench
from probeforge.ats.freeze import ats_frozen_hashes
from probeforge.ats.infogain import AtsInfoGain
from probeforge.ats.nextstep import planned_next, reading_text
from probeforge.faults.model import Fault

MEASURING = ("measure_voltage", "measure_resistance", "manual_operation_check", "read_position_indicator")


def scenario(faults):
    b = AtsBench(faults=faults)
    b.lose_utility()
    b.step(60.0)
    return b


def run(faults, hook: bool):
    plans = []
    p = AtsInfoGain(scenario(faults), AtsBench().n, model_key="true",
                    on_update=(lambda pl, step: plans.append((len(pl.tb.log), planned_next(pl)))) if hook else None)
    d = p.run()
    return p.tb.log, d, plans


def test_helper_changes_nothing_and_plans_the_step_taken():
    for faults in ([Fault("H1", "open", "W7_TS4-W7_P7")], [Fault("TS", "open", "A-B")]):
        log_a, d_a, _ = run(faults, hook=False)
        log_b, d_b, plans = run(faults, hook=True)
        assert json.dumps(log_a, default=str) == json.dumps(log_b, default=str) and d_a == d_b
        assert plans and plans[-1][1]["tool"] == "submit_diagnosis"
        for at, plan in plans:
            taken = next(e for e in log_b[at:] if e["tool"] != "update_hypotheses")
            assert taken["tool"] == plan["tool"]
            if plan["tool"] in MEASURING:
                assert all(taken["args"].get(k) == v for k, v in plan["args"].items())
                assert len(plan["outcomes"]) >= 2  # a planned reading splits the remaining causes
                assert sum(o["n"] for o in plan["outcomes"]) >= plan["causes_left"]


def test_reading_text():
    assert reading_text("measure_voltage", 0.0) == "0 V"
    assert reading_text("measure_resistance", "open") == "open"
    assert reading_text("manual_operation_check", (True, ("open", 0.0))) == "moves, reads open, 0 ohm"


def test_frozen_modules_unchanged():
    assert ats_frozen_hashes() == {"ats_hybrid_read": "08b4676a5c4b", "ats_hybrid_pipeline": "8a9c95c16c71",
                                   "ats_hybrid_explain": "1a468df099ba", "ats_infogain": "2eff9c8764c1", "ats_sheet_crops": "5687e25c8ce3"}
