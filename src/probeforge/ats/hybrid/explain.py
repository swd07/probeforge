"""Explanation step of Hybrid v2 on the ATS bench (decision D41): what a field technician acts on, so it is built and
checked in code rather than left to prompt wording.

Input, all from the transcribed model and the planner (never the true netlist): the diagnosed part in words (its kind,
terminals and the circuit it sits in), every step with its probe points, the observed reading, what a fault-free switch
would read at that moment (the same steps replayed on the fault-free model), whether the step probed the diagnosed
part, and how many candidates were left; actions (isolation, the manual check) as actions, not raw values; the causes
no reading separates (twins).

Output: strict JSON (what failed, evidence per step, the part to act on as one of the model's part ids, the action),
rendered to text in code. Check: the part to act on must be the diagnosed part or a twin, and the action sentences may
name no other part and must call the part by its kind (coil, wire, pin...). On a mismatch the model is asked once more
with the reason; then a template built from the diagnosis is used. `check_text` scores any explanation text, so the
old free-text explanations are measured by the same rule.

Consequential faults (decision D42): when the remaining candidates carry the diagnosed root with further faults (the
documented burnout chain: both cut-off contacts of one side stuck closed, and the coil they burnt), the action must
name all of them: the root part and its co-root (the same misadjustment) first, then the damaged part (test and
replace), because a repaired coil alone burns again at the next transfer.

Safety wording (decision D47): the isolation instruction is not left to the model. Code puts one fixed sentence
(SAFETY) before every action, in model texts and templates; the check requires it before any repair instruction,
rejects energized-work and bypass wording in the action part (unless negated: "without paralleling sources" is fine),
and the evidence may cite only steps that were executed.
"""

import json
import re
import time

from probeforge.agent.loop import _cost
from probeforge.ats.infogain import _fingerprint, _scenario_benches, _value
from probeforge.ats.tools import AtsToolBox
from probeforge.faults.model import Fault
from probeforge.hybrid.llm import EM_DASH, Usage
from probeforge.sim.netlist import Netlist
from probeforge.tools import approve_all

KIND_TEXT = {
    "solenoid": "the transfer switch operating coil (solenoid)",
    "cutoff_n": "a TS control (cut-off) contact in the operating coil circuit",
    "cutoff_e": "a TS control (cut-off) contact in the operating coil circuit",
    "aux_n": "a TS auxiliary (position) contact",
    "aux_e": "a TS auxiliary (position) contact",
    "main_n": "a main power contact of the transfer switch",
    "main_e": "a main power contact of the transfer switch",
    "wire": "a harness wire",
    "pin": "a pin of the controller plug and jack",
    "input": "a controller input",
    "contact_no": "a relay contact inside the controller",
    "contact_nc": "a relay contact inside the controller",
    "point": "a terminal block point",
    "breaker_pole": "a pole of the Normal source breaker",
}
# words that name the part by its kind; the action must use one of them
KIND_WORDS = {
    "solenoid": ("coil", "solenoid"), "cutoff_n": ("contact",), "cutoff_e": ("contact",), "aux_n": ("contact",),
    "aux_e": ("contact",), "main_n": ("contact",), "main_e": ("contact",), "wire": ("wire",),
    "pin": ("pin", "plug", "jack", "connector"), "input": ("input", "controller"),
    "contact_no": ("relay", "controller"), "contact_nc": ("relay", "controller"), "point": ("terminal", "point"),
    "breaker_pole": ("breaker", "pole"), "mechanism": ("mechanism", "operator", "linkage", "jam"),
}
ACTION_VERBS = re.compile(r"\b(check|inspect|repair|replace|tighten|test|look|verify|reseat|fix|swap|clean|adjust|free|"
                          r"lubricate|retest|examine|trace)\w*\b|\bcorrect(?=\s+(?:the|a|an|this|that|its)\b)", re.I)
SAFETY = ("Before any work: open 52U, lock out and tag the generator, and prove both sources dead at the work point "
          "with a voltmeter.")
REPAIR_WORDS = re.compile(r"\b(repair|replace|tighten|reseat|fix|swap|adjust|lubricate|rewire|install)\w*\b", re.I)
# D50: unsafe wording in three kinds (an external audit passed the D47 list with synonyms and with text placed before
# the isolation sentence). Always unsafe, anywhere in the text:
ALWAYS_UNSAFE = re.compile(r"\b(bypass\w*|jumper\w*|defeat\w*|parallel\w*\s+(?:the\s+|both\s+)?(?:sources?|generator|utility|"
                           r"supplies)|skip\w*\s+(?:the\s+)?(?:lock-?out|isolation|tag-?out)|without\s+(?:isolat|lock)\w*)", re.I)
# unsafe in the action part (in the evidence these words describe a reading, "the coil stayed energized"):
STATE_UNSAFE = re.compile(r"\b(energi[sz]ed|energi[sz]ing|while live|live (?:circuit|conductor|terminal|part)s?|under load|"
                          r"(?:with\s+(?:the\s+)?)?power(?:ed)?\s+on|hot)\b", re.I)
# re-energizing is unsafe when a repair instruction follows it ("restore the sources and verify" after a repair is not):
REENERGIZE = re.compile(r"\b(re-?energi[sz]\w*|restor\w*\s+(?:the\s+|both\s+)?(?:power|sources?|supply|supplies|utility)|"
                        r"close\s+(?:the\s+)?52U|start\s+(?:the\s+)?generator|turn\s+(?:the\s+)?power\s+(?:back\s+)?on)", re.I)
# a negation covers its own clause only: it stops at punctuation and at "and", "then", "but"
NEGATION = re.compile(r"\b(no|not|without|never|nor|avoid|do not|don't)\b(?:(?!\b(?:and|then|but)\b)[^.;,]){0,80}$", re.I)
TWIN_NOTE = "no reading separates: "
STILL_NOTE = "still possible: "

PROMPT = """You are writing for a field technician. A transfer switch (ASCO Series 300 Group G) did not transfer the load
during a utility outage. An information-gain planner took readings on the switch and reached this result:
{result}

The part concerned: {name} ({part})
{twins}{consequences}Every other cause the planner considered was ruled out by the readings, so every other part that was measured is
behaving normally for the switch's present position. The switch stayed on Normal; a fault-free switch would already
have transferred to Emergency, so for readings away from the part concerned its values differ for that reason alone
and are not shown.

Steps (observed reading; for steps that probe the part concerned, what a fault-free switch would read at that moment;
candidate faults left before and after):
{steps}

Return JSON: "what_failed" (one sentence that calls the part exactly "{name}"), "evidence" (2 to 4 items, each a step
number and one sentence on what that reading shows; a reading marked normal for the present position is not a fault),
"action_part" (the id of the part an authorized person should repair or inspect next: {allowed_text}), and "action"
({action_rule} With both sources isolated and locked out, within the safety limits: no bypassing interlocks, no
paralleling sources, no manual operation under load). Plain English, no dashes as punctuation.<<RETRY>>"""
ACTION_ONE = ('one or two sentences: what an authorized person should do next on "{name}" only; name no other part in '
              'the action, not even as a location.')
ACTION_CHAIN = ('two or three sentences: first fix the root cause, {roots}; then test {damaged} and replace it if it is '
                'burnt; say why the order matters: a new {damaged} alone burns again at the next transfer while the '
                'root cause remains. '
                'Use exactly these names, in this order, and name no other part.')


def _faults_in(note: str, prefix: str) -> list[Fault]:
    out = []
    for item in note[len(prefix):].split(", "):
        target, _, mode = item.strip().rpartition(" ")
        comp, _, part = target.partition(":")
        if comp and mode:
            out.append(Fault(comp, mode, part or None))
    return out


def allowed_targets(diagnosis: dict, consequences: list[str] | None = None) -> list[str]:
    """Part ids (or component ids for a whole-device fault) the explanation may tell the technician to act on: the
    diagnosed part, its twins and (if given) the parts of consequential faults of the same root cause, such as the coil
    a stuck cut-off contact burnt."""
    note = str(diagnosis.get("note") or "")
    if diagnosis.get("outcome") != "diagnosed":
        return [f.target if f.part else f.component for f in _faults_in(note, STILL_NOTE)] if note.startswith(STILL_NOTE) else []
    first = f"{diagnosis['component']}:{diagnosis['part']}" if diagnosis.get("part") else diagnosis["component"]
    twins = [f.target if f.part else f.component for f in _faults_in(note, TWIN_NOTE)] if note.startswith(TWIN_NOTE) else []
    return list(dict.fromkeys([first, *twins, *(consequences or [])]))


def consequence_split(planner, diagnosis: dict) -> tuple[list[str], list[str]]:
    """The other faults in the remaining candidates with the diagnosed root (the documented burnout chain), as
    (co-roots, damaged parts): a co-root shares the root's failure mode (the same misadjustment), a damaged part was
    burnt by it."""
    if diagnosis.get("outcome") != "diagnosed":
        return [], []
    root = Fault(diagnosis["component"], diagnosis["failure_mode"], diagnosis.get("part") or None)
    co, dmg = [], []
    for c in planner.cands:
        if c.faults and c.faults[0] == root:
            for f in c.faults[1:]:
                (co if f.mode == root.mode else dmg).append(f.target if f.part else f.component)
    return list(dict.fromkeys(co)), list(dict.fromkeys(dmg))


def consequence_targets(planner, diagnosis: dict) -> list[str]:
    """Parts of the other faults in the remaining candidates with the diagnosed root (co-roots, then damaged parts)."""
    co, dmg = consequence_split(planner, diagnosis)
    return co + dmg


def display_name(n: Netlist, target: str) -> str:
    """The name the explanation must use for a part (it carries the kind word the check looks for)."""
    if target not in n.parts:
        return f"{target} transfer mechanism"
    p = n.parts[target]
    comp, name = p.component, p.name
    return {"solenoid": f"operating coil {comp} {name}", "cutoff_n": f"cut-off contact {comp} {name}",
            "cutoff_e": f"cut-off contact {comp} {name}", "aux_n": f"auxiliary contact {comp} {name}",
            "aux_e": f"auxiliary contact {comp} {name}", "main_n": f"main contact {comp} {name}",
            "main_e": f"main contact {comp} {name}", "wire": f"harness wire W{name.split('_', 1)[0][1:]}",
            "pin": f"plug and jack pin {name}", "input": f"controller input {name}",
            "contact_no": f"{comp} relay contact {name} (inside the controller)",
            "contact_nc": f"{comp} relay contact {name} (inside the controller)",
            "point": f"terminal block point {comp} {name}"}.get(p.kind, f"{comp} {name}")


def _kind(n: Netlist, target: str) -> str:
    return n.parts[target].kind if target in n.parts else "mechanism"


def _aliases(n: Netlist, pid: str) -> list[re.Pattern]:
    """Ways an explanation names a part: its terminal pair (with or without the component prefix), and for wires
    'wire 7' / 'W7', for pins 'P7' / 'J7', for the coil 'coil' / 'solenoid'."""
    p = n.parts[pid]
    comp, name = p.component, p.name
    pats = []
    if p.kind == "wire":
        num = name.split("_", 1)[0][1:]  # W7_TS4-W7_P7 -> 7, W9A_TB15-... -> 9A
        pats += [rf"\bwire\s*W?{num}\b", rf"\bW{num}\b", rf"\bW{num}_(?:TS|TB|P)\w*"]  # also a wire end label
    elif p.kind == "pin":
        a, _, b = name.partition("-")
        # the pin itself, not a wire end that lands on it ("wire 7 from TS 4 to P7" names the wire)
        pats += [rf"\bpins?\s*(?:{a}|{b}|{a[1:]})\b", rf"\b{a}\s*(?:-|/|and|to)\s*{b}\b"]
    elif p.kind == "input":
        pats += [rf"\b(?:CP|controller input)[: ]?\s*{name}\b"]
    else:
        a, _, b = name.partition("-")
        if a and b:
            pre = rf"(?:{comp}[: ]?\s*)?"
            sep = r"\s*(?:-|to|and|through)\s*"
            notstep = r"(?<!step\s)(?<!steps\s)"  # "steps 1 and 2" is not breaker pole 1-2
            pats += [rf"\b{notstep}{pre}{re.escape(a)}{sep}{pre}{re.escape(b)}\b",
                     rf"\b{notstep}{pre}{re.escape(b)}{sep}{pre}{re.escape(a)}\b"]
        if p.kind == "solenoid":
            pats += [r"\bcoil\b", r"\bsolenoid\b"]
    return [re.compile(x, re.I) for x in pats]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def check_text(text: str, diagnosis: dict, n: Netlist, strict: bool = True, consequences: list[str] | None = None,
               damaged: list[str] | None = None) -> list[str]:
    """Problems with an explanation, empty if it passes: the action sentences (those with an action verb) must name
    the diagnosed part or a twin, by its kind, and no other part. For insufficient information, they may name only
    parts still possible (or none). strict=False also accepts an action that refers back by kind ("repair the wire")
    to the diagnosed part named elsewhere in the text; a wrong part in the action fails either way. With consequential
    faults (D42) the action must also name every one of them by its kind, and the damaged parts only after the root
    (the root part or a co-root): fix the cause first, then test and replace what it damaged."""
    allowed = allowed_targets(diagnosis)  # the action must name one of these
    excused = allowed_targets(diagnosis, consequences)  # and may also name consequential parts
    actions = [s for s in _sentences(text) if ACTION_VERBS.search(s)]
    if not actions:
        return ["no action sentence"] if diagnosis.get("outcome") == "diagnosed" else []
    act = " ".join(actions)
    named = {pid for pid in n.parts if any(p.search(act) for p in _aliases(n, pid))}
    problems = []
    others = sorted(x for x in named if x not in excused and n.parts[x].component not in excused)
    if others:
        problems.append(f"the action names parts that are not the diagnosed part: {', '.join(others)}")
    if diagnosis.get("outcome") == "diagnosed":
        hit = [a for a in allowed if a in named or (a not in n.parts and any(w in act.lower() for w in KIND_WORDS["mechanism"]))]
        if not hit and not strict:
            hit = [a for a in allowed if a in n.parts and any(p.search(text) for p in _aliases(n, a))]
        if not hit:
            problems.append(f"the action does not name the diagnosed part ({', '.join(allowed)})")
        elif not any(any(w in act.lower() for w in KIND_WORDS.get(_kind(n, a), ())) for a in hit):
            problems.append(f"the action does not call {hit[0]} by its kind ({' or '.join(KIND_WORDS.get(_kind(n, hit[0]), ()))})")
        problems += _chain_problems(act, n, allowed, consequences or [], damaged or [])
    return problems + safety_problems(text)


def safety_problems(text: str) -> list[str]:
    """D47, extended by D50: the fixed isolation sentence is present and no repair instruction comes before it; no
    bypass, jumper, paralleling of sources, skipped lockout or work without isolation anywhere in the text; no
    energized-work wording in the action part after the sentence; no re-energizing followed by a repair. Mentions
    negated in their own clause ("without paralleling sources", "do not bypass interlocks") pass. A fixed list:
    it narrows what the model can say, it is not a safety review of the text."""
    at = text.find(SAFETY)
    if at < 0:
        return ["the isolation sentence is missing"]
    problems = []
    if REPAIR_WORDS.search(text[:at]):
        problems.append("a repair instruction comes before the isolation sentence")
    after = text[at + len(SAFETY):]

    def unnegated(pattern: re.Pattern, scope: str) -> list[re.Match]:
        return [m for m in pattern.finditer(scope) if not NEGATION.search(scope[:m.start()])]

    bad = [m.group(0) for m in unnegated(ALWAYS_UNSAFE, text) + unnegated(STATE_UNSAFE, after)]
    bad += [m.group(0) for m in unnegated(REENERGIZE, text) if REPAIR_WORDS.search(text[m.end():])]
    if bad:
        problems.append(f"the text asks for unsafe work: {', '.join(dict.fromkeys(bad))}")
    return problems


def _first_at(text: str, n: Netlist, pid: str) -> int | None:
    pos = [m.start() for p in _aliases(n, pid) for m in [p.search(text)] if m] if pid in n.parts else []
    return min(pos) if pos else None


def _chain_problems(act: str, n: Netlist, allowed: list[str], consequences: list[str], damaged: list[str]) -> list[str]:
    """The consequential-fault rule (D42) on the action text."""
    out = []
    missing = [c for c in consequences if _first_at(act, n, c) is None]
    if missing:
        out.append(f"the action does not name the consequential faults of the same root cause ({', '.join(missing)})")
    unkind = [c for c in consequences if c not in missing and not any(w in act.lower() for w in KIND_WORDS.get(_kind(n, c), ()))]
    if unkind:
        out.append(f"the action does not call {', '.join(unkind)} by its kind")
    roots = [x for x in (_first_at(act, n, r) for r in allowed + [c for c in consequences if c not in damaged]) if x is not None]
    for d in damaged:
        at = _first_at(act, n, d)
        if at is not None and roots and at < min(roots):
            out.append(f"the action names the damaged part {d} before the root cause: fix the root cause first")
    return out


# ------------------------------------------------------------------ input

def part_text(n: Netlist, target: str) -> str:
    if target not in n.parts:
        comp = n.components.get(target)
        return f"{target}: the whole {comp.label if comp else target} (its mechanism), not one part"
    p = n.parts[target]
    ends = []
    for t in (p.a, p.b):
        others = [x for x in n.nets[n.terminal_net[t]] if x != t][:4]
        ends.append(f"{t} (also connected to {', '.join(others) or 'nothing else'})")
    return f"{target}: {KIND_TEXT.get(p.kind, p.kind)} of {n.components[p.component].label}, between {ends[0]} and {ends[1]}"


def _reading(tool: str, value) -> str:
    if isinstance(value, tuple) and value[:1] == ("error",):
        return "not taken (refused by the policy in that state)"
    if tool == "measure_voltage":
        return f"{value} V"
    if tool == "measure_resistance":
        return "open" if value == "open" else f"{value} ohm"
    if tool == "read_position_indicator":
        return f"mechanism on {value}"
    if tool == "manual_operation_check" and isinstance(value, tuple):
        moved, ohms = value
        return ("the mechanism moved to the other position" if moved else "the mechanism did not move") + \
            ", reading there " + ", ".join("open" if v == "open" else f"{v} ohm" for v in ohms)
    if tool == "isolate_sources" and isinstance(value, tuple):
        return f"done; load {'powered' if value[0] else 'not powered'}, controller shows {value[1]}"
    return str(value)


def _action(tool: str, args: dict) -> str:
    if tool in ("measure_voltage", "measure_resistance"):
        return f"{'voltage' if tool == 'measure_voltage' else 'resistance'} {args['point_a']} to {args['point_b']}"
    if tool == "manual_operation_check":
        pts = ", ".join(f"{r['point_a']} to {r['point_b']}" for r in args.get("readings", []))
        return f"manual operation check (sources isolated), then resistance {pts} at the other position"
    if tool == "isolate_sources":
        return "isolate both sources (52U open, generator locked out): an action, not a reading"
    return tool.replace("_", " ")


def _points(tool: str, args: dict) -> set[str]:
    if tool == "manual_operation_check":
        return {p for r in args.get("readings", []) for p in (r["point_a"], r["point_b"])}
    return {args[k] for k in ("point_a", "point_b") if k in args}


def steps_text(planner, targets: list[str]) -> str:
    """Each step with the fault-free model's reading at the same moment (the same steps replayed on it)."""
    n = planner.models[0]
    key = (planner.model_key, 0) if planner.model_key is not None else ("nets", _fingerprint(n))
    faults, base = _scenario_benches(n, key)[0]
    healthy = None
    if faults == ():
        healthy = AtsToolBox(base.clone(), approver=approve_all, action_s=planner.tb.action_s)
        healthy.initial_observation()
    probe_terms = set()
    for tgt in targets:
        if tgt in n.parts:
            p = n.parts[tgt]
            probe_terms |= {p.a, p.b, n.terminal_net[p.a], n.terminal_net[p.b]}
    lines = []
    for s in planner.steps:
        h = "unknown"
        if healthy is not None:
            healthy.step = s.step - 1
            try:
                h = _reading(s.tool, _value(s.tool, healthy.call(s.tool, s.args)))
            except Exception:  # noqa: BLE001 - a step the fault-free model cannot take
                h = "not available"
        probes = bool(_points(s.tool, s.args) & probe_terms)
        if s.tool == "isolate_sources":
            ref = "an action"
        elif probes:
            ref = f"probes the part concerned; a fault-free switch would read {h}"
        else:
            ref = "normal for the present position (explained by the diagnosed fault)"
        lines.append(f"step {s.step}: {_action(s.tool, s.args)} -> observed {_reading(s.tool, s.value)}; {ref}; "
                     f"candidates left {s.before} -> {s.after}")
    return "\n".join(lines) or "(only the controller panel at step 0)"


# ------------------------------------------------------------------ model call, check, fallback

def _schema(ids: list[str]) -> dict:
    return {"type": "json_schema", "json_schema": {"name": "explanation", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": ["what_failed", "evidence", "action_part", "action"],
        "properties": {
            "what_failed": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                    "required": ["step", "meaning"],
                                                    "properties": {"step": {"type": "integer"}, "meaning": {"type": "string"}}}},
            "action_part": {"type": "string", "enum": ids},
            "action": {"type": "string"}}}}}


def _call(client, usage: Usage, prompt: str, ids: list[str], effort: str) -> dict:
    t0 = time.perf_counter()
    resp = client.chat.completions.create(model=usage.model, reasoning_effort=effort, response_format=_schema(ids),
                                          messages=[{"role": "user", "content": prompt}])
    u = resp.usage
    prompt_t, completion = (u.prompt_tokens, u.completion_tokens) if u else (0, 0)
    details = getattr(u, "prompt_tokens_details", None) if u else None
    cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
    cost = _cost(usage.model, prompt_t, cached, completion)
    usage.turns += 1
    usage.prompt_tokens += prompt_t
    usage.cached_tokens += cached
    usage.completion_tokens += completion
    usage.cost_usd += cost
    reply = (resp.choices[0].message.content or "").replace(EM_DASH, ", ")
    usage.turn_log.append({"turn": usage.turns, "purpose": "explanation", "effort": effort, "prompt_tokens": prompt_t,
                           "cached_tokens": cached, "completion_tokens": completion, "cost_usd": round(cost, 5),
                           "latency_s": round(time.perf_counter() - t0, 1), "text": reply})
    return json.loads(reply)


def _cap(s: str) -> str:
    s = s.strip()
    return s[:1].upper() + s[1:]


def render(x: dict) -> str:
    """What failed, the evidence, the fixed isolation sentence (code, not the model), then the model's action."""
    ev = " ".join(f"Step {e['step']}: {_cap(e['meaning']).rstrip('.')}." for e in x.get("evidence", []))
    parts = (_cap(x["what_failed"]).rstrip(".") + ".", ev, SAFETY, _cap(x["action"]))
    return " ".join(p for p in parts if p).replace(EM_DASH, ", ")


REPAIR_VERB = {"solenoid": "replace the", "wire": "repair or replace", "pin": "reseat or replace", "input": "replace the "
               "controller for", "contact_no": "replace the controller for", "contact_nc": "replace the controller for",
               "cutoff_n": "adjust or replace the", "cutoff_e": "adjust or replace the", "aux_n": "adjust or replace the",
               "aux_e": "adjust or replace the", "point": "repair", "mechanism": "free and lubricate the transfer mechanism"}


def _short(tool: str, args: dict) -> str:
    if tool in ("measure_voltage", "measure_resistance"):
        return f"{'voltage' if tool == 'measure_voltage' else 'resistance'} {args['point_a']} to {args['point_b']}"
    if tool == "manual_operation_check":
        return "manual operation with the sources isolated"
    return tool.replace("_", " ")


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def template(diagnosis: dict, planner, n: Netlist) -> str:
    """Fallback built from the diagnosis and the readings only (no model text). Readings away from the diagnosed part
    are marked normal for the present position, so they cannot read as a second fault."""
    ev = [s for s in planner.steps if s.after < s.before and s.tool != "isolate_sources"][-3:]
    terms = set()
    co, dmg = consequence_split(planner, diagnosis)
    for tgt in allowed_targets(diagnosis, co + dmg):
        if tgt in n.parts:
            p = n.parts[tgt]
            terms |= {p.a, p.b, n.terminal_net[p.a], n.terminal_net[p.b]}
    cites = "; ".join(f"step {s.step}, {_short(s.tool, s.args)}: {_reading(s.tool, s.value)}"
                      + ("" if _points(s.tool, s.args) & terms or not terms else " (normal for the present position)")
                      for s in ev)
    if diagnosis.get("outcome") != "diagnosed":
        still = [display_name(n, x) for x in allowed_targets(diagnosis)]
        return (f"No single cause can be named from the readings the policy allows. Still possible: "
                f"{', '.join(still) or 'see the hypotheses'}. Evidence: {cites or 'the controller panel'}. {SAFETY} "
                "Then an authorized person tests each of these parts in turn; a relay contact inside the controller "
                "cannot be probed, so for those the controller is the repair.")
    first = allowed_targets(diagnosis)[0]
    kind = _kind(n, first)
    name = display_name(n, first)
    twins = f" No reading separates {' and '.join(diagnosis['note'][len(TWIN_NOTE):].split(', '))}; it is the same part, so the action is the same." \
        if str(diagnosis.get("note", "")).startswith(TWIN_NOTE) else ""
    mode = diagnosis["failure_mode"].replace("_", " ")
    if co or dmg:  # D42: the root cause first, then the damaged part
        roots = _join([name, *(f"the {display_name(n, c)}" for c in co)])
        damaged = _join([display_name(n, d) for d in dmg]) if dmg else ""
        then = (f" Then test the {damaged} and replace it if it is burnt. The order matters: a "
                "replacement alone burns again at the next transfer while the root cause remains."
                if dmg else "")
        return (f"The {name} is {mode}{f', with the {damaged} damaged by it' if dmg else ''}.{twins} Evidence: "
                f"{cites or 'the panel'}. {SAFETY} Then an authorized person should first "
                f"{REPAIR_VERB.get(kind, 'repair')} {roots}.{then}")
    return (f"The {name} is {mode}.{twins} Evidence: {cites or 'the panel'}. {SAFETY} Then "
            f"an authorized person should {REPAIR_VERB.get(kind, 'repair')} {name if kind != 'mechanism' else ''}".rstrip() + ".")


def explain(client, usage: Usage, planner, diagnosis: dict, effort: str = "low") -> tuple[str, dict]:
    """The explanation and its record (attempts, check results, whether the template was used). Insufficient
    information gets the template: with no single part to act on, a model text risks presenting a guess as a finding."""
    n = planner.models[0]
    if diagnosis.get("outcome") != "diagnosed":
        return template(diagnosis, planner, n), {"attempts": [], "template": True, "reason": "insufficient information"}
    co, damaged = consequence_split(planner, diagnosis)
    consequences = co + damaged
    targets = allowed_targets(diagnosis)
    d = diagnosis
    res = (f"{d['component']} {d.get('part', '')} {d['failure_mode']}" if d.get("outcome") == "diagnosed"
           else f"insufficient information: {d.get('note', '')}")
    twins = (f"No reading separates these causes: {d['note'][len(TWIN_NOTE):]} (the same part: the same action)."
             if str(d.get("note", "")).startswith(TWIN_NOTE) else "")
    ids = sorted(set(n.parts) | set(n.components) | {"none"})
    part = "; ".join(part_text(n, t) for t in targets) or "(no single part: insufficient information)"
    allowed_text = f"one of {', '.join(targets)}" if targets else "none, or a part still possible"
    name = display_name(n, targets[0]) if targets else "the parts still possible"
    cons = ""
    if co:
        cons += f"The same root cause (one misadjustment) also affects: {_join([display_name(n, c) for c in co])}.\n"
    if damaged:
        cons += f"The root cause also damaged (burnt): {_join([display_name(n, c) for c in damaged])}.\n"
    roots = _join([name, *(display_name(n, c) for c in co)])
    rule = (ACTION_CHAIN.format(roots=roots, damaged=_join([display_name(n, c) for c in damaged]) or "nothing else")
            if consequences else ACTION_ONE.format(name=name))
    base = PROMPT.format(result=res, name=name, part=part, twins=twins, consequences=cons, action_rule=rule,
                         steps=steps_text(planner, targets + consequences), allowed_text=allowed_text)
    record = {"attempts": [], "template": False}
    executed = {0} | {s.step for s in planner.steps}  # step 0: the first panel look
    retry = ""
    for _ in range(2):
        try:
            x = _call(client, usage, base.replace("<<RETRY>>", retry), ids, effort)
            text = render(x)
            problems = check_text(text, d, n, consequences=consequences, damaged=damaged)
            cited = {e["step"] for e in x.get("evidence", [])} - executed
            if cited:
                problems.append(f"the evidence cites steps that were not executed: {sorted(cited)}")
            if targets and x["action_part"] not in targets + consequences and d.get("outcome") == "diagnosed":
                problems.insert(0, f"action_part {x['action_part']} is not the diagnosed part ({', '.join(targets)})")
        except Exception as e:  # noqa: BLE001 - a failed call falls through to the template
            text, problems = "", [f"call failed: {type(e).__name__}: {e}"]
        record["attempts"].append({"text": text, "problems": problems})
        if not problems:
            return text, record
        retry = ("\n\nYour previous answer was rejected: " + "; ".join(problems) +
                 (f'. In the action, first {roots}, then the damaged part, by exactly these names.' if consequences
                  else f'. In the action, call the part exactly "{name}" and name no other part.'))
    record["template"] = True
    return template(d, planner, n), record
