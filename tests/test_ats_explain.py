"""Explanation step of Hybrid v2 on the ATS bench (D41, D42, D47): the text check, the structured input, one retry on a
mismatch and the template fallback, the fixed isolation sentence and the safety and citation rules, with a scripted fake
model (no API calls)."""

import json

import pytest
from types import SimpleNamespace

from probeforge.ats import AtsBench
from probeforge.ats.hybrid.explain import (SAFETY, allowed_targets, check_text, consequence_split, explain, render,
                                           steps_text, template)
from probeforge.ats.hybrid.read import build, to_netlist
from probeforge.ats.infogain import AtsInfoGain
from probeforge.faults.model import Fault
from probeforge.hybrid.llm import Usage
from tests.test_ats_hybrid import perfect_transcription

N = to_netlist(build(perfect_transcription()))
S = SAFETY + " "  # code puts it before every action (D47)
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
    assert check_text(S + "Replace the operating coil TS A-B.", COIL, N) == []
    assert "TS:6-7" in check_text(S + "Inspect the coil connections at TS 6 to TS 7.", COIL, N)[0]
    assert "by its kind" in check_text(S + "Inspect and repair the A to B contacts.", COIL, N)[0]
    wire = {"outcome": "diagnosed", "component": "H1", "part": "W7_TS4-W7_P7", "failure_mode": "open"}
    assert check_text(S + "Inspect wire 7 from TS 4 to P7 and repair it.", wire, N) == []
    assert check_text("Readings at steps 1 and 2 agree. " + S + "Replace wire 7.", wire, N) == []  # not breaker pole 1-2
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


def test_consequential_faults_root_first_then_the_damaged_part():
    """D42: the burnout chain (both cut-offs stuck closed, the coil they burnt) needs the root fixed first, then the
    coil tested and replaced; naming the root alone, or the coil first, fails the check."""
    b = AtsBench(netlist=N, faults=[Fault("TS", "stuck_closed", "8-9"), Fault("TS", "stuck_closed", "71-72"),
                                    Fault("TS", "burnt", "A-B")])
    b.lose_utility()
    b.step(60.0)
    p = AtsInfoGain(b, N)
    d = p.run()
    assert (d["component"], d["part"]) in (("TS", "8-9"), ("TS", "71-72"))
    co, dmg = consequence_split(p, d)
    assert dmg == ["TS:A-B"] and len(co) == 1
    root, other = f"cut-off contact TS {d['part']}", f"cut-off contact {co[0].replace(':', ' ')}"
    kw = {"consequences": co + dmg, "damaged": dmg}
    good = f"{S}Adjust or replace the {root} and the {other}. Then test the operating coil TS A-B and replace it if burnt."
    assert check_text(good, d, N, **kw) == []
    assert "consequential" in check_text(f"{S}Adjust or replace the {root}.", d, N, **kw)[0]
    assert "before the root" in " ".join(check_text(f"{S}Replace the operating coil TS A-B, then adjust the {root} and the {other}.", d, N, **kw))
    tpl = template(d, p, N)
    assert check_text(tpl, d, N, **kw) == [] and "burns again at the next transfer" in tpl
    assert check_text(S + "Correct the misadjustment of the " + root + " and the " + other + ". Then test the operating coil TS A-B.", d, N, **kw) == []
    fake = Fake([reply(d["component"] + ":" + d["part"], good[len(S):], what=f"The {root} did not open.")])
    out, rec = explain(fake, Usage(), p, d)
    assert "first fix the root cause" in fake.prompts[0] and "burnt" in fake.prompts[0]
    assert not rec["template"] and check_text(out, d, N, **kw) == []


def test_unsafe_actions_and_invented_citations_are_rejected():
    """D47 (from the external review): energized work, a bypass, a repair before the isolation sentence or a missing
    isolation sentence fail the check; negated safety limits pass; evidence may cite only executed steps."""
    assert check_text("Replace the operating coil TS A-B while both sources are energized.", COIL, N) == ["the isolation sentence is missing"]
    assert "unsafe work: energized" in check_text(S + "Replace the operating coil TS A-B while both sources are energized.", COIL, N)[0]
    assert "unsafe work: bypass" in " ".join(check_text(S + "Bypass the interlock and replace the operating coil TS A-B.", COIL, N)).lower()
    assert "before the isolation" in " ".join(check_text("Replace the operating coil TS A-B. " + S, COIL, N))
    assert check_text(S + "Replace the operating coil TS A-B without bypassing interlocks, without paralleling sources and "
                      "without manual operation under load.", COIL, N) == []
    assert check_text(S + "Replace the operating coil TS A-B. Do not bypass interlocks or parallel sources or operate "
                      "manually under load.", COIL, N) == []  # one negation covers the clause
    assert "unsafe work" in " ".join(check_text(S + "Without delay, replace the operating coil TS A-B under load.", COIL, N))
    p, d = coil_planner()
    invented = reply("TS:A-B", "Replace the operating coil TS A-B.")
    invented["evidence"] = [{"step": 99, "meaning": "a reading that never happened"}]
    out, rec = explain(Fake([invented, invented]), Usage(), p, d)
    assert rec["template"] and "not executed: [99]" in rec["attempts"][0]["problems"][-1] and check_text(out, d, N) == []


def test_the_isolation_sentence_comes_from_code_before_the_action():
    text = render(reply("TS:A-B", "Replace the operating coil TS A-B."))
    assert text.index(SAFETY) < text.index("Replace the operating coil") and text.count(SAFETY) == 1
    p, d = coil_planner()
    assert SAFETY in template(d, p, N) and SAFETY in template({"outcome": "insufficient_information", "note": ""}, p, N)


@pytest.mark.parametrize("text", [
    S + "Re-energize the switch, then replace the operating coil TS A-B.",
    S + "Restore both sources, then replace the operating coil TS A-B.",
    S + "Close 52U and start the generator, then replace the operating coil TS A-B.",
    S + "With power on, replace the operating coil TS A-B.",
    S + "Replace the operating coil TS A-B hot.",
    S + "Replace the operating coil TS A-B without isolating the sources.",
    S + "Skip the lockout and replace the operating coil TS A-B.",
    "Bypass the interlock. " + S + "Replace the operating coil TS A-B.",
    "Jumper the cut-off contacts to test. " + S + "Replace the operating coil TS A-B.",
    S + "There is no reason to delay and bypass the interlock when you replace the operating coil TS A-B.",
])
def test_the_audits_unsafe_wordings_fail_the_check(text):
    """D50: every wording the external audit passed through the D47 check is now rejected."""
    assert any("unsafe work" in p for p in check_text(text, COIL, N)), text


@pytest.mark.parametrize("text", [
    S + "Replace the operating coil TS A-B. After the repair, restore the sources and verify the transfer.",
    S + "Replace the operating coil TS A-B. Do not bypass interlocks or parallel sources or operate manually under load.",
    S + "Replace the operating coil TS A-B without bypassing interlocks and without paralleling sources.",
    "Step 2: The paralleled readings agree and the coil stayed energized. " + S + "Replace the operating coil TS A-B.",
])
def test_safe_wording_still_passes(text):
    assert check_text(text, COIL, N) == [], text
