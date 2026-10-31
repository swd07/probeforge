"""Explanation step of Hybrid v2 on the ATS bench (D41): the text check, the structured input, one retry on a mismatch
and the template fallback, with a scripted fake model (no API calls)."""

import json
from types import SimpleNamespace

from probeforge.ats import AtsBench
from probeforge.ats.hybrid.explain import allowed_targets, check_text, explain, steps_text, template
from probeforge.ats.hybrid.read import build, to_netlist
from probeforge.ats.infogain import AtsInfoGain
from probeforge.faults.model import Fault
from probeforge.hybrid.llm import Usage
from tests.test_ats_hybrid import perfect_transcription

N = to_netlist(build(perfect_transcription()))
COIL = {"outcome": "diagnosed", "component": "TS", "part": "A-B", "failure_mode": "open", "confidence": 0.5,
        "note": "no reading separates: TS:A-B open, TS:A-B burnt"}


class Fake:
    """chat.completions.create returns the scripted JSON replies in order and records the prompts."""

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.prompts.append(kw["messages"][0]["content"])
        assert kw["response_format"]["json_schema"]["strict"]
        msg = SimpleNamespace(content=json.dumps(self.replies.pop(0)))
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=msg)])


def reply(part, action, what="The operating coil TS A-B is open."):
    return {"what_failed": what, "evidence": [{"step": 2, "meaning": "208 V across the coil, the switch did not move"}],
            "action_part": part, "action": action}


def coil_planner():
    b = AtsBench(netlist=N, faults=[Fault("TS", "open", "A-B")])
    b.lose_utility()
    b.step(60.0)
    p = AtsInfoGain(b, N)
    d = p.run()
    return p, d


def test_check_text_rules():
    assert check_text("Replace the operating coil TS A-B with both sources isolated.", COIL, N) == []
    assert "TS:6-7" in check_text("Inspect the coil connections at TS 6 to TS 7.", COIL, N)[0]
    assert "by its kind" in check_text("Inspect and repair the A to B contacts.", COIL, N)[0]
    wire = {"outcome": "diagnosed", "component": "H1", "part": "W7_TS4-W7_P7", "failure_mode": "open"}
    assert check_text("Inspect wire 7 from TS 4 to P7 and repair it.", wire, N) == []
    assert check_text("Readings at steps 1 and 2 agree. Replace wire 7.", wire, N) == []  # not breaker pole 1-2
    assert allowed_targets(COIL) == ["TS:A-B"]


def test_input_has_healthy_values_parts_and_actions_and_a_good_answer_passes():
    p, d = coil_planner()
    text = steps_text(p, allowed_targets(d))
    assert "probes the part concerned; a fault-free switch would read" in text
    assert "normal for the present position (explained by the diagnosed fault)" in text
    assert "isolate both sources" in text and "an action, not a reading" in text
    fake = Fake([reply("TS:A-B", "With both sources isolated and locked out, replace the operating coil TS A-B.")])
    out, rec = explain(fake, Usage(), p, d)
    assert "operating coil (solenoid)" in fake.prompts[0] and "No reading separates" in fake.prompts[0]
    assert len(fake.prompts) == 1 and not rec["template"] and check_text(out, d, N) == []


def test_mismatch_is_asked_again_once_then_the_template_is_used():
    p, d = coil_planner()
    wrong = reply("TS:6-7", "Inspect the cut-off contact TS 6 to TS 7.")
    good = reply("TS:A-B", "Replace the operating coil TS A-B.")
    fake = Fake([wrong, good])
    out, rec = explain(fake, Usage(), p, d)
    assert len(fake.prompts) == 2 and "rejected" in fake.prompts[1] and not rec["template"] and "coil TS A-B" in out
    fake = Fake([wrong, wrong])
    out, rec = explain(fake, Usage(), p, d)
    assert rec["template"] and out == template(d, p, N) and check_text(out, d, N) == []


def test_insufficient_information_gets_the_template_listing_every_part_still_possible():
    p, _ = coil_planner()
    d = {"outcome": "insufficient_information", "confidence": 0.0,
         "note": "still possible: SE:X1-J2 stuck_open, ER:J1-X1 stuck_open"}
    fake = Fake([])
    out, rec = explain(fake, Usage(), p, d)
    assert fake.prompts == [] and rec["template"]
    assert "No single cause" in out and "SE relay contact X1-J2" in out and "ER relay contact J1-X1" in out
    assert check_text(out, d, N) == []
