"""Hybrid v2 on the ATS bench: Read, Model, Plan, Verify, Explain (the same pipeline as the relay-panel hybrid, whose
modules stay frozen; this package only imports their generic pieces).

1. Read: Muse Spark reads the drawing sheets of 978741 three times (read.read_consensus); terminals the reads disagree
   about become uncertain regions, added to the model's own flags.
2. Model: the fault model is generated from the transcribed netlist (catalog plus the documented compound fault).
   The model must reproduce the documented fault-free sequence of the Group G guide (healthy outage and retransfer:
   the event list below); a model that does not is sent to the repair step before planning.
3. Plan: the ATS information-gain planner on the transcribed netlist, joint with alternative wirings of the flagged
   regions (hybrid/uncertainty.py generates them, unchanged); the readings come from the real bench through the same
   toolbox and policy as the agent.
4. Verify: a reading no candidate explains asks Muse Spark for a corrected transcription. A correction is accepted
   only if it rewires terminals inside flagged regions (or a region it names), still reproduces the documented
   fault-free sequence, and explains every reading so far; after two rejected proposals no more are requested.
5. Explain: Muse Spark writes a short technician-facing explanation citing the decisive readings.

The model calls never see the true netlist or the injected fault.
"""

import copy
import re
import time
from dataclasses import dataclass, field

import yaml

from probeforge.ats.bench import AtsBench
from probeforge.ats.hybrid.read import build, chat_images, parse_reply, to_netlist
from probeforge.ats.infogain import AtsInfoGain
from probeforge.ats.tools import approve_standard_only
from probeforge.hybrid.llm import Usage, chat
from probeforge.hybrid.repair import rewired
from probeforge.hybrid.uncertainty import alternatives, pin_groups

# the documented fault-free sequence (Group G User's Guide pages 29, 30): a healthy outage and retransfer
HEALTHY_EVENTS = ["N Source Not Accepted", "Engine Start", "E Source Accepted", "Transfer N to E", "N Source Accepted",
                  "Transfer E to N", "Engine Stop", "E Source Not Accepted"]
MAX_VARIANTS = 6
MAX_REJECTED = 2


_healthy_cache: dict = {}


def _on_course(events: list[str]) -> bool:
    return events == HEALTHY_EVENTS[:len(events)]


def healthy_sequence(n) -> tuple[bool, list[str]]:
    """Does the model reproduce the documented healthy outage and retransfer? Returns (ok, the events it gives).
    The simulation stops as soon as an event departs from the documented order (cached by netlist content)."""
    from probeforge.ats.infogain import _fingerprint

    key = _fingerprint(n)
    if key in _healthy_cache:
        return _healthy_cache[key]
    try:
        b = AtsBench(netlist=n)
        b.lose_utility()
        events: list[str] = []
        for _ in range(12):  # the outage, in 5 s chunks: stop at the first event out of the documented order
            b.step(5)
            events = [e["event"] for e in b.indicators()["events"]]
            if not _on_course(events):
                break
        if _on_course(events):
            b.restore_utility()
            b.step(b.s["t_3a"] + b.s["t_2e"] + 30)
            events = [e["event"] for e in b.indicators()["events"]]
        result = (events == HEALTHY_EVENTS and b.position == "N", events)
    except Exception as e:  # noqa: BLE001 - a model the bench cannot run fails the check
        result = (False, [f"simulation error: {type(e).__name__}: {e}"])
    _healthy_cache[key] = result
    return result


def progress(events: list[str]) -> int:
    """How far a model follows the documented sequence: the length of the correct start of its event list."""
    k = 0
    while k < len(events) and k < len(HEALTHY_EVENTS) and events[k] == HEALTHY_EVENTS[k]:
        k += 1
    return k


def where_it_breaks(n) -> tuple[str, list[str]]:
    """Where the model's own healthy outage departs from the documented sequence, and the terminals of that circuit
    (computed on the transcribed model only; the documented controller ports are those of the Group G guide)."""
    from probeforge.ats.bench import POS_14A, POS_14B, POS_COMMON, SENSE_E, SENSE_N

    def circuit(*seeds: str) -> list[str]:
        comps = {s.split(":")[0] for s in seeds}
        terms = {s for s in seeds if s in n.terminal_net}
        terms |= {t for p in n.parts.values() if p.component in comps for t in (p.a, p.b)}
        return sorted({x for t in terms for x in n.nets[n.terminal_net[t]]} | terms)  # with the nets they join

    try:
        b = AtsBench(netlist=n)
        b.lose_utility()
        b.step(30)
    except Exception as e:  # noqa: BLE001
        relays = sorted(c for c, s in n.components.items() if s.type == "relay" and c not in ("SE", "ER", "NR"))
        if relays:  # the Group G controller relays (guide): SE, ER, NR
            return (f"the controller relays are SE, ER and NR (Group G guide), but the transcription names {relays}",
                    sorted(t for p in n.parts.values() if p.component in relays for t in (p.a, p.b)))
        return f"the bench cannot run the transcription ({type(e).__name__}: {e})", []
    ev = [e["event"] for e in b.indicators()["events"]]
    m = b.indicators()["metering"]
    if "Engine Start" not in ev:
        return f"the controller does not see the Normal source fail (Normal metering {m['Normal']} V)", circuit(*SENSE_N)
    if b.generator_state() == "stopped":
        return ("after NR drops out (engine start signal) the engine start contact between TB/TS 14 and TB/TS 15 does "
                "not close, so the generator never starts"), circuit("TBTS:14", "TBTS:15", "NR:J8", "NR:J9", "NR:J17")
    if "E Source Accepted" not in ev:
        return (f"the generator runs but the controller does not accept it: the Emergency line voltages it reads are "
                f"{m['Emergency']} V"), circuit(*SENSE_E)
    if "Transfer N to E" not in ev and "Position Error" not in ev:
        b2 = AtsBench(netlist=n)
        b2.lose_utility()
        b2.step(12.5)
        return (f"Emergency is accepted and ER is energized but the switch does not transfer (voltage across the TS "
                f"solenoid A-B right after the command: {b2.coil_voltage()} V)"), circuit("TS:A", "TS:B", "SE:J2", "SE:J5", "ER:J1", "ER:J16")
    if "Position Error" in ev:
        return "the switch transfers but the controller reports Position Error (TS position contacts 14A / 14B)", circuit(
            POS_COMMON, POS_14A, POS_14B, "TS:17")
    return "the healthy retransfer to Normal departs from the documented sequence", []


MAX_EVALUATED = 12


def variants(data: dict, flags: list[dict], limit: int = MAX_VARIANTS) -> list:
    """Alternative wirings of the flagged regions (as for the relay panel: same-side terminals of same-kind parts),
    only for a model that reproduces the documented sequence, and only alternatives that reproduce it too (at most
    MAX_EVALUATED alternatives are simulated)."""
    try:
        n = to_netlist(data)
    except Exception:  # noqa: BLE001
        return []
    if not healthy_sequence(n)[0]:
        return []
    out, evaluated = [], 0
    for f in flags:
        region = {t for t in f["terminals"] if t in n.terminal_net}
        comps = sorted({t.split(":")[0] for t in region})
        groups = pin_groups(n, region, comps)
        if not groups:
            continue
        for alt in alternatives(data, groups, limit=limit - len(out)):
            if evaluated >= MAX_EVALUATED:
                break
            evaluated += 1
            try:
                v = to_netlist(alt)
            except Exception:  # noqa: BLE001
                continue
            if healthy_sequence(v)[0]:
                out.append(v)
        if len(out) >= limit or evaluated >= MAX_EVALUATED:
            break
    return out


REPAIR_PROMPT = """You transcribed the attached transfer switch drawing sheets earlier into the compact YAML below. A diagnosis
is running on the real switch with that transcription as the model. {problem}

Your transcription:
```yaml
{raw}
```

Regions you or the repeated reads were unsure about:
{flags}

Readings taken on the real switch so far (step: action -> result):
{readings}

Check the drawing sheets again where the transcription could be wrong and reply with the complete corrected YAML in the
same format inside one ```yaml block. Change only what the drawing shows differently; if you change wiring outside the
listed regions, add that place to `uncertain` with the reason. Then one line starting with "Explanation:" saying what
you changed and why."""

EXPLAIN_PROMPT = """You are writing for a field technician. A transfer switch (ASCO Series 300 Group G) did not transfer the load
during a utility outage. A diagnosis planner took these readings on the switch (step: action -> result):
{readings}

Its result: {result}

Write 3 to 5 short sentences in plain English: what failed, which readings prove it (cite step numbers like "step 4"),
and what an authorized person should check or repair next, within the safety limits (no bypassing interlocks, no
paralleling sources, no manual operation under load). Do not use dashes as punctuation."""


def readings_text(planner: AtsInfoGain) -> str:
    lines = []
    for s in planner.steps:
        what = s.tool if not s.args.get("point_a") else f"{s.tool} {s.args['point_a']} to {s.args['point_b']}"
        lines.append(f"step {s.step}: {what} -> {s.value}")
    return "\n".join(lines) or "(only the controller panel at step 0)"


@dataclass
class Repairer:
    client: object
    usage: Usage
    images: list[bytes]
    raw: dict
    flags: list[dict]
    effort: str = "medium"
    rejected: int = 0
    records: list[dict] = field(default_factory=list)

    def propose(self, problem: str, planner: AtsInfoGain | None) -> tuple[dict | None, dict]:
        prompt = REPAIR_PROMPT.format(problem=problem, raw=yaml.safe_dump(self.raw, sort_keys=False, width=200),
                                      flags="\n".join(f"- {f['terminals']}: {f['reason']}" for f in self.flags) or "(none)",
                                      readings=readings_text(planner) if planner else "(none yet)")
        reply = chat_images(self.client, self.usage, "repair", prompt, self.images, self.effort)
        m = re.search(r"Explanation:\s*(.*)", reply)
        rec = {"problem": problem, "explanation": m.group(1).strip() if m else ""}
        try:
            raw = parse_reply(reply)
            data = build(raw)
            return {"raw": raw, "data": data}, rec
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {e}"
            return None, rec

    def judge(self, old: dict, new: dict, planner: AtsInfoGain | None, region: list[str] = (),
              need_progress: bool = False) -> list[str]:
        """need_progress (the Model step): accept a fix that gets further along the documented sequence without
        losing what worked; otherwise (a conflict during a run) the whole sequence must pass and the corrected model
        must explain every reading."""
        reasons = []
        allowed = ({t for f in self.flags for t in f["terminals"]} | set(region)
                   | {t for f in new["data"].get("uncertain") or [] for t in f["terminals"]})
        # a terminal the old model did not have, on a component of the named circuit (a contact given to the other
        # relay of the same block, for example) belongs to that circuit
        old_terms = {x for v in old["nets"].values() for x in v}
        comps = {x.split(":")[0] for x in region}
        allowed |= {x for v in new["data"]["nets"].values() for x in v if x not in old_terms and x.split(":")[0] in comps}
        moved = rewired(old, new["data"]) - allowed
        if moved:
            reasons.append(f"rewires terminals outside every flagged region: {sorted(moved)[:8]}")
        ok, events = healthy_sequence(to_netlist(new["data"]))
        if need_progress:
            before, after = progress(healthy_sequence(to_netlist(old))[1]), progress(events)
            if after <= before and not ok:
                reasons.append(f"does not get further along the documented sequence ({after} of {len(HEALTHY_EVENTS)} "
                               f"events in order, before {before}; gives {events})")
        elif not ok:
            reasons.append(f"breaks the documented fault-free sequence (gives {events})")
        if planner is not None and not reasons:
            trial = copy.copy(planner)
            trial.models = [to_netlist(new["data"])]
            trial.model_key = None
            trial._build()
            if not trial.cands:
                reasons.append("no candidate fault of the corrected model explains every reading")
        return reasons

    def __call__(self, old: dict, problem: str, planner: AtsInfoGain | None, region: list[str] = (),
                 need_progress: bool = False, cap: int = MAX_REJECTED):
        if self.rejected >= cap:
            return None
        new, rec = self.propose(problem, planner)
        if new is None:
            self.rejected += 1
            self.records.append({**rec, "rejected": rec.get("error")})
            return None
        rec["diff"] = sorted(rewired(old, new["data"]))
        reasons = self.judge(old, new, planner, region, need_progress)
        if reasons:
            self.rejected += 1
            self.records.append({**rec, "rejected": "; ".join(reasons)})
            return None
        self.records.append(rec)
        self.raw = new["raw"]
        self.flags = list(new["data"].get("uncertain") or []) + self.flags
        return new["data"]


@dataclass
class AtsHybridResult:
    diagnosis: dict
    outcome: str
    planner: AtsInfoGain
    usage: Usage
    explanation: str = ""
    seconds: float = 0.0
    healthy_check: dict = field(default_factory=dict)
    corrections: list[dict] = field(default_factory=list)
    variants: int = 0


MODEL_ATTEMPTS = 4


def prepare_model(client, usage: Usage, data: dict, raw: dict, flags: list[dict], images: list[bytes],
                  effort: str = "medium", attempts: int = MODEL_ATTEMPTS) -> tuple[dict, dict, list[dict], dict]:
    """Model step, once per transcription (shared by every case): check the documented fault-free sequence and, while
    the model fails it, ask Muse Spark for a correction of the circuit where its own simulation departs. A correction is
    accepted if it gets further along the sequence without losing what worked (and stays in a flagged or named
    region); the check then reruns to find the next problem (at most `attempts` proposals). The problem text and the
    parts to check come from the transcribed model and the documented sequence only, never from the true netlist.
    Returns (data, raw, flags, record); record["versions"] holds every accepted model (for evaluation)."""
    repairer = Repairer(client, usage, images, raw, list(flags), effort)
    ok, events = healthy_sequence(to_netlist(data))
    record = {"ok": ok, "events": events, "attempts": [], "versions": [data], "progress": [progress(events)]}
    while not ok and client is not None and len(record["attempts"]) < attempts:
        where, region = where_it_breaks(to_netlist(data))
        record.setdefault("where", []).append(where)
        new = repairer(data, "The transcription does not reproduce the documented fault-free sequence of the Group G "
                             f"controller: a healthy outage and retransfer gives {events}, expected {HEALTHY_EVENTS}. "
                             f"Simulating your transcription, {where}. Check that circuit on the drawing: "
                             f"{', '.join(region) if region else '(see the sheets)'}.", None, region,
                       need_progress=True, cap=attempts)
        record["attempts"].append(repairer.records[-1])
        if new is None:
            continue
        data = new
        ok, events = healthy_sequence(to_netlist(data))
        record.update(ok=ok, events=events, repaired=True)
        record["versions"].append(data)
        record["progress"].append(progress(events))
        repairer.records[-1]["accepted"] = f"{progress(events)} of {len(HEALTHY_EVENTS)} documented events in order"
    if ok:
        warm(data, repairer.flags)  # build the candidate benches once, shared by every case
    return data, repairer.raw, repairer.flags, record


def warm(data: dict, flags: list[dict]) -> None:
    """Simulate every candidate of the model and its wiring variants from the scenario start (cached by content)."""
    from probeforge.ats.infogain import _fingerprint, _scenario_benches

    for n in [to_netlist(data), *variants(data, flags)]:
        _scenario_benches(n, ("nets", _fingerprint(n)))


def run_ats_hybrid(bench: AtsBench, client, data: dict, raw: dict, images: list[bytes], *, usage: Usage | None = None,
                   flags: list[dict] | None = None, approver=approve_standard_only, repair: bool = True,
                   do_explain: bool = True, on_event=None, on_update=None, repair_effort: str = "medium",
                   explain_effort: str = "low", healthy: dict | None = None) -> AtsHybridResult:
    """Diagnose one case with a prepared model (prepare_model: the fault-free sequence is checked once per model)."""
    usage = usage or Usage(effort=repair_effort)
    t0 = time.perf_counter()
    flags = list(flags if flags is not None else data.get("uncertain") or [])
    repairer = Repairer(client, usage, images, raw, flags, repair_effort)
    state = {"data": data}
    if healthy is None:
        ok, events = healthy_sequence(to_netlist(data))
        healthy = {"ok": ok, "events": events}

    def on_conflict(ctx: dict):
        if not repair:
            return None
        new = repairer(state["data"], f"At step {ctx['step'].step} the reading ({ctx['step'].tool} -> {ctx['step'].value}) "
                                      "is not explained by any fault of the transcribed circuit.", ctx["planner"])
        if new is None:
            return None
        state["data"] = new
        return [to_netlist(new), *variants(new, repairer.flags)]

    alts = variants(state["data"], repairer.flags)
    planner = AtsInfoGain(bench, to_netlist(state["data"]), approver=approver, variants=alts, on_event=on_event,
                          on_update=on_update, on_conflict=on_conflict)
    if not healthy.get("ok"):
        # the model does not reproduce the documented fault-free sequence: no planning on it (the answer could only
        # be insufficient information); the technician is asked to confirm the transcription
        planner.tb.initial_observation()
        diagnosis = {"outcome": "insufficient_information", "confidence": 0.0,
                     "evidence": [{"step": 0, "type": "functional_test", "observation": "controller panel"}],
                     "note": "the transcribed model does not reproduce the documented fault-free sequence "
                             f"({healthy.get('events')}); confirm the transcription before diagnosing on it"}
        planner.tb.call("submit_diagnosis", diagnosis)
        result = AtsHybridResult(diagnosis, "insufficient_information", planner, usage, healthy_check=healthy,
                                 corrections=repairer.records, variants=0)
        result.seconds = time.perf_counter() - t0
        return result
    try:
        diagnosis = planner.run()
    except Exception as e:  # noqa: BLE001 - a model the bench cannot simulate: hand over honestly
        planner.notes.append(f"the transcribed model cannot be simulated: {type(e).__name__}: {e}")
        planner.cands = []
        if not planner.tb.log:
            planner.tb.initial_observation()
        diagnosis = planner.submit()
    if not healthy.get("ok") and diagnosis.get("outcome") == "diagnosed":
        # the model does not reproduce the documented fault-free sequence: never a confident answer on it
        lead = f"{diagnosis['component']} {diagnosis.get('part', '')} {diagnosis['failure_mode']}".strip()
        diagnosis = {"outcome": "insufficient_information", "confidence": 0.0, "evidence": diagnosis["evidence"][:1],
                     "note": f"the transcribed model does not reproduce the documented fault-free sequence; the planner's "
                             f"lead on it was {lead}; confirm the transcription first"}
        planner.tb.diagnosis = diagnosis
    result = AtsHybridResult(diagnosis, diagnosis.get("outcome", "error"), planner, usage, healthy_check=healthy,
                             corrections=repairer.records, variants=len(alts))
    if do_explain:
        try:
            d = diagnosis
            res = (f"{d['component']} {d.get('part', '')} {d['failure_mode']} (confidence {d['confidence']})"
                   if d.get("outcome") == "diagnosed" else f"insufficient information: {d.get('note', '')}")
            result.explanation = chat(client, usage, "explanation", EXPLAIN_PROMPT.format(readings=readings_text(planner),
                                                                                          result=res), None, explain_effort)
        except Exception as e:  # noqa: BLE001 - a failed explanation must not lose the diagnosis
            usage.error = f"explanation failed: {type(e).__name__}: {e}"
    result.seconds = time.perf_counter() - t0
    return result
