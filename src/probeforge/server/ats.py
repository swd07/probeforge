"""ATS bench sessions for the web backend (agent and engineer), on the same WebSocket as the relay panel.

As for the relay panel, the browser never receives the injected fault while a session runs: tool events carry what
the actor saw, panel snapshots what a technician at the switch sees (the controller face, the sources, the load, the
UPS, the mechanism position flag). The fault, its observational twins and the true live nets are sent only in "done".

The hybrid session runs the frozen Hybrid v2 (probeforge.ats.hybrid) on a saved transcription (a recorded run's model
step, scenarios/transcriptions/ats/) or on a live re-read of the drawing crops (local only, cost shown first); the
planner's next step is sent before every reading (probeforge.ats.nextstep, read from the planner's update hook).

After the diagnosis the session stays open for the authorized intervention (isolate, repair, restore) through the
same toolbox and policy; the UPS status flow ends at "Transfer verified" only when the simulator confirms the load on
Emergency with the position confirmed by the controller.
"""

import itertools
import json
import os
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import yaml

from probeforge.agent.client import MUSE_SPARK
from probeforge.ats.agent import run_ats_agent
from probeforge.ats import transcriptions
from probeforge.ats.ambiguity import signature
from probeforge.ats.bench import INTERNAL_NETS, REPAIR_KINDS, AtsBench
from probeforge.ats.faults import COMPONENT_MODES, PART_MODES, all_faults, validate
from probeforge.ats.hybrid.pipeline import HEALTHY_EVENTS, healthy_sequence, prepare_model, run_ats_hybrid, warm
from probeforge.ats.hybrid.read import SHEET_DIR, SHEETS, read_consensus, sheet_images, to_netlist
from probeforge.ats.infogain import AtsInfoGain, Step, _value
from probeforge.ats.nextstep import planned_next
from probeforge.ats.policy import RULES
from probeforge.ats.tools import AtsApprovalRequest, AtsToolBox, approve_standard_only
from probeforge.eval.scoring import grade
from probeforge.eval.spend import EST_PER_AGENT_RUN_USD, SpendLedger, SpendLimitError
from probeforge.eval.trace import describe_diagnosis, make_trace
from probeforge.faults.model import Fault
from probeforge.hybrid.llm import Usage
from probeforge.sim.schematic import render_svg

ROOT = Path(__file__).resolve().parents[3]
CASES_DIR = ROOT / "scenarios" / "ats"
ENGINEER_DIR = ROOT / "scenarios" / "engineer_traces" / "ats"
COMPARE_DIR = ROOT / "runs" / "compare"
BENCH = AtsBench()
NETLIST = BENCH.n
SVG = render_svg(NETLIST)
OUTAGE_S = 60.0  # every session starts 60 s after the Normal source failed (as the batch runs)
LIVE_V = 20.0
APPROVAL_TIMEOUT_S = 600
FLOW = ["Fault detected", "Diagnosis in progress", "Root cause identified", "Awaiting authorized intervention",
        "Power restored", "Transfer verified"]
MANUAL_TOOLS = {"read_panel", "read_event_log", "read_metering", "read_position_indicator", "wait", "measure_voltage", "measure_resistance",
                "isolate_sources", "restore_sources", "manual_operation_check", "repeat_transfer_attempt",
                "perform_action", "submit_diagnosis"}
INTERVENTION_TOOLS = MANUAL_TOOLS - {"submit_diagnosis"}  # after the diagnosis, for the authorized person
EST_HYBRID_SAVED_USD = 0.02  # explanation only (recorded runs: about $0.006 per case)
EST_HYBRID_LIVE_USD = 1.00  # 3 reads plus up to 4 repairs (recorded model steps: $0.28 and $0.48)
PLAN_PAUSE_S = 1.0  # UI pace only: the plan stays on screen this long before the planner takes it (no effect on results)
LIVE_READ_TEXT = "about $0.30 to $1.00 and 4 to 7 minutes (3 Muse Spark reads of the drawing crops, then the model check)"


def _f(d: dict) -> Fault:
    return Fault(d["component"], d["mode"], d.get("part"))


def load_cases() -> dict[str, dict]:
    return {d["id"]: d for d in (yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(CASES_DIR.glob("*.yaml")))}


CASES = load_cases()


def _outage(faults: list[Fault]) -> AtsBench:
    b = AtsBench(faults=faults)
    b.lose_utility()
    b.step(OUTAGE_S)
    return b


def _face(b: AtsBench) -> tuple:
    i = b.indicators()
    return (tuple(sorted(i["lights"].items())), i["display"], tuple(i["alarms"]), i["generator"], i["load_powered"],
            tuple(i["metering"]["Emergency"]))


_visible: list[Fault] | None = None
_pool_lock = threading.Lock()


def visible_pool() -> list[Fault]:
    """Catalog faults that show on the controller panel during the outage (the random choice; faults that only
    matter on retransfer would look like a healthy switch)."""
    global _visible
    with _pool_lock:
        if _visible is None:
            healthy = _face(_outage([]))
            _visible = [f for f in all_faults(NETLIST) if _face(_outage([f])) != healthy]
    return _visible


_sigs: dict | None = None
_sig_lock = threading.Lock()


def catalog_signatures() -> dict:
    global _sigs
    visible_pool()  # the random choice needs it first
    with _sig_lock:
        if _sigs is None:
            _sigs = {f: signature([f]) for f in all_faults(NETLIST)}
    return _sigs


_sig_thread: threading.Thread | None = None


def warm_signatures() -> None:
    """Start the twin signatures in the background (about 15 s), needed only for the result card."""
    global _sig_thread
    if _sig_thread is None:
        _sig_thread = threading.Thread(target=catalog_signatures, daemon=True)
        _sig_thread.start()


_warm_lock = threading.Lock()
_warm_events: dict[str, threading.Event] = {}


def warm_transcription(tid: str) -> threading.Event:
    """Simulate every candidate of a saved transcription in the background (about 80 s, once per transcription and
    server process; the frozen planner caches them by netlist content). The event is set when they are ready."""
    with _warm_lock:
        ev = _warm_events.get(tid)
        if ev is None:
            ev = _warm_events[tid] = threading.Event()

            def job():
                try:
                    t = transcriptions.load(tid)
                    if healthy_sequence(to_netlist(t["data"]))[0]:
                        warm(t["data"], t["flags"])
                finally:
                    ev.set()

            threading.Thread(target=job, daemon=True).start()
    return ev


def live_read_available() -> bool:
    return all((SHEET_DIR / s).exists() for s in SHEETS)


def meta() -> dict:
    warm_signatures()  # the browser asks for meta when the ATS bench is chosen: precompute the pool and twins then
    warm_transcription(transcriptions.DEFAULT)
    comps = []
    for c in NETLIST.components.values():
        parts = [{"name": p.name, "kind": p.kind, "modes": list(PART_MODES.get(p.kind, ()))} for p in c.parts]
        modes = list(COMPONENT_MODES.get(c.type, ()))
        if modes or any(p["modes"] for p in parts):
            comps.append({"id": c.id, "type": c.type, "label": c.label, "modes": modes, "parts": parts})
    return {
        "model": MUSE_SPARK,
        "title": NETLIST.title,
        "neutral": "NN",
        # symptom only: the description would name the fault
        "scenarios": [{"id": cid, "symptom": c["symptom"]} for cid, c in CASES.items()],
        "components": comps,
        "repairs": {a: [p.id for p in NETLIST.parts.values() if p.kind in kinds] or ["CP"] for a, kinds in REPAIR_KINDS.items()},
        "limits": [{"action": a, "tier": t, "condition": c} for a, t, c in RULES],
        "ups_autonomy_s": BENCH.a["ups_autonomy_s"],
        "action_s": 30,
        "flow": FLOW,
        "transcriptions": transcriptions.available(),
        "default_transcription": transcriptions.DEFAULT,
        "live_read": {"available": live_read_available(), "estimate": LIVE_READ_TEXT},
    }


def pick(msg: dict) -> tuple[list[Fault], str, dict | None]:
    """Faults, where they came from, and the case (None for a random fault)."""
    if msg.get("fault"):  # test / demo hook (?fault= in the URL), never offered in the UI
        target, _, mode = str(msg["fault"]).strip().partition(" ")
        comp, _, part = target.partition(":")
        f = Fault(comp, mode.strip(), part or None)
        validate(NETLIST, f)
        return [f], "fault chosen by URL", None
    if msg.get("source") == "scenario":
        case = CASES[msg["scenario"]]
        return [_f(x) for x in (case.get("faults") or [case["fault"]])], f"ATS dev scenario {case['id']}", case
    pool = visible_pool()
    return [random.SystemRandom().choice(pool)], f"random ATS fault (any of the {len(pool)} visible on the panel)", None


def snapshot(b: AtsBench, flow: int) -> dict:
    i = b.indicators()
    mech = "moving" if b.moving else {"N": "Normal", "E": "Emergency"}[b.position]
    return {"ats": True, "lights": i["lights"], "display": i["display"], "alarms": i["alarms"], "metering": i["metering"],
            "events": i["events"], "normal_source": i["normal_source"], "generator": i["generator"],
            "load_powered": i["load_powered"], "ups": i["ups"], "time_s": i["time_s"], "position": mech,
            "isolated": b.isolated, "flow": flow}


def _reading_text(r: dict) -> str:
    v = f"{r['volts']} V" if "volts" in r else (r["ohms"] if r.get("ohms") == "open" else f"{r.get('ohms')} ohm")
    return f"{r['point_a']} to {r['point_b']}: {v}"


def describe(entry: dict) -> str:
    """One line for an executed step (cited evidence on the approval card)."""
    r, tool = entry["result"], entry["tool"]
    if "volts" in r or "ohms" in r:
        return f"{'Voltage' if 'volts' in r else 'Resistance'} {_reading_text(r)}"
    if tool == "manual_operation_check":
        rs = r.get("readings_at_other_position") or r.get("readings") or []
        return f"Manual operation: {'moved' if r.get('moved_to_other_position') else 'did not move'}" + (
            "; " + "; ".join(_reading_text(x) for x in rs) if rs else "")
    if tool == "repeat_transfer_attempt":
        return "Repeat transfer, during the command: " + "; ".join(_reading_text(x) for x in r.get("readings_during_command", []))
    return tool.replace("_", " ")


def sequence(log: list[dict]) -> list[str]:
    """Every step after the first panel look, as one line each (blocked and refused steps marked)."""
    out = []
    for e in log[1:]:
        if e["tool"] in ("update_hypotheses", "submit_diagnosis", "get_schematic"):
            continue
        if e["verdict"] == "block":
            out.append(f"blocked: {e['tool'].replace('_', ' ')}")
        elif not e["executed"]:
            out.append(f"not done: {e['tool'].replace('_', ' ')} ({str(e['result'].get('error', ''))[:60]})")
        else:
            out.append(describe(e))
    return out


TWIN_NOTE = "no reading separates: "


def diagnosis_text(diagnosis: dict | None, outcome: str) -> tuple[str, bool]:
    """The diagnosis as shown, and whether it names observational twins. A planner diagnosis whose note lists causes
    no reading separates reads "TS A-B open or burnt (no reading separates them; same repair)" instead of a split
    confidence, which reads as doubt."""
    d = diagnosis or {}
    note = str(d.get("note") or "")
    if outcome != "diagnosed" or not note.startswith(TWIN_NOTE):
        return describe_diagnosis(diagnosis, outcome), False
    items = [x.strip().rsplit(" ", 1) for x in note[len(TWIN_NOTE):].split(", ") if " " in x.strip()]
    targets = {target for target, _ in items}
    if len(targets) == 1:
        return f"{targets.pop().replace(':', ' ')} {' or '.join(m for _, m in items)} (no reading separates them; same repair)", True
    return " or ".join(f"{target.replace(':', ' ')} {m}" for target, m in items) + " (no reading separates them)", True


def column(trace: dict, judged: dict, strong: int, live_approvals: bool) -> dict:
    """One column of the ATS comparison."""
    d = trace["diagnosis"] or {}
    text, twins = diagnosis_text(trace["diagnosis"], trace["outcome"])
    return {"runner": trace["runner"], "diagnosis": text,
            "confidence": None if twins else d.get("confidence"), "verdict": judged["verdict"], "measurements": trace["measurements"],
            "redundant": trace["redundant_measurements"], "blocked": trace["policy"]["blocked"],
            "approvals": trace["policy"]["approval_requests"], "strong_approvals": strong,
            "approvals_denied": trace["policy"]["approvals_denied"], "seconds": trace["seconds"],
            "cost_usd": trace["cost_usd"], "sequence": sequence(trace["tool_log"]),
            "approvals_by": "answered live in this session" if live_approvals else "batch rules",
            "assisted": bool(trace.get("assisted"))}


def engineer_trace(faults: list[Fault]) -> dict | None:
    """A recorded engineer trace for exactly these faults (real engineers only: walkthrough traces are deleted)."""
    want = sorted(f.to_dict().items() for f in faults)
    for p in sorted(ENGINEER_DIR.glob("*.json"), reverse=True):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if sorted(Fault.from_dict(x).to_dict().items() for x in rec.get("faults", [])) == want:
            return rec
    return None


class AtsSession:
    """Shared by the ATS agent and engineer sessions: one bench, approvals, enriched tool events, intervention."""

    mode = "agent"
    bench_name = "ats"

    def __init__(self, faults: list[Fault], source: str, case: dict | None, emit):
        self.faults, self.source, self.case, self.emit = faults, source, case, emit
        self.bench = _outage(faults)
        self.tb: AtsToolBox | None = None
        self.flow = 0
        self.cancelled = False
        self.done = False  # the diagnosis is in (the session stays open for the intervention)
        self.closed = False
        self.trace: dict | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple[threading.Event, list]] = {}
        self._lock = threading.Lock()

    # flow -------------------------------------------------------------------------

    def _advance_flow(self, entry: dict | None = None) -> None:
        i = self.bench.indicators()
        if self.flow == 0 and entry and entry["executed"]:
            self.flow = 1
        if self.flow >= 3 and entry and entry["executed"] and entry["tool"] == "restore_sources":
            self.flow = max(self.flow, 4)
        if self.flow >= 3 and i["load_powered"] and i["lights"]["Load on Emergency"] and not self.bench.isolated:
            self.flow = 5  # the simulator verifies the transfer: load fed, position confirmed by the controller

    # called from worker threads ---------------------------------------------------

    def approver(self, req: AtsApprovalRequest) -> bool:
        rid = next(self._ids)
        event, answer = threading.Event(), [False]
        self._pending[rid] = (event, answer)
        log = {e["step"]: e for e in (self.tb.log if self.tb else [])}
        cited = [{"step": s, "text": describe(log[s])} for s in req.args.get("evidence_steps") or [] if s in log]
        self.emit({"type": "approval_request", "id": rid, "step": req.step, "tool": req.tool,
                   "args": {k: v for k, v in req.args.items() if k not in ("readings", "target_id")},
                   "policy_reason": req.policy_reason, "agent_reason": req.agent_reason, "strong": req.strong,
                   "facts": list(req.facts), "evidence": cited})
        event.wait(APPROVAL_TIMEOUT_S)
        self._pending.pop(rid, None)
        if self.cancelled:
            raise Cancelled()
        self.emit({"type": "approval_answer", "id": rid, "approved": answer[0]})
        return answer[0]

    def on_event(self, ev: dict) -> None:
        if self.cancelled:
            raise Cancelled()
        if ev["type"] == "tool":
            self._advance_flow(ev)
            ev = {**ev, "probes": self._probes(ev), "panel": snapshot(self.bench, self.flow)}
        self.emit(ev)

    def _probes(self, ev: dict) -> list[dict]:
        r = ev["result"]
        items = []
        if "volts" in r or "ohms" in r:
            items.append(r)
        items += r.get("readings_during_command", []) + r.get("readings_at_other_position", []) + r.get("readings", [])
        out = []
        for x in items:
            na, nb = NETLIST.terminal_net.get(x["point_a"], x["point_a"]), NETLIST.terminal_net.get(x["point_b"], x["point_b"])
            out.append({"kind": "V" if "volts" in x else "R", "a": x["point_a"], "b": x["point_b"],
                        "value": x.get("volts", x.get("ohms")), "net_a": na, "net_b": nb,
                        "term_a": x["point_a"] if x["point_a"] in NETLIST.terminal_net else NETLIST.nets[na][0],
                        "term_b": x["point_b"] if x["point_b"] in NETLIST.terminal_net else NETLIST.nets[nb][0]})
        return out

    def judge(self, diagnosis: dict | None, outcome: str) -> dict:
        answers = ([_f(self.case.get("root_cause") or self.case["fault"])] + [_f(x) for x in self.case.get("also_accepted") or []]
                   if self.case else list(self.faults))
        sig = signature(self.faults)
        twins = [f for f, s in catalog_signatures().items() if s == sig and f not in answers]
        d = diagnosis if outcome == "diagnosed" else {"outcome": outcome}
        grades = [grade(d, a, False, twins) for a in answers]
        g = next((x for x in grades if x["correct"]), grades[0])
        if outcome != "diagnosed":
            v = "justified" if g["justified"] else "no diagnosis"
        else:
            v = "correct" if g["correct"] else "justified" if g["justified"] else "pole open" if g["pole_open"] else "wrong"
        others = [str(f) for f in self.faults if f not in answers]
        fault = " or ".join(str(a) for a in answers) + (f" (root cause; also present: {', '.join(others)})" if others else "")
        return {"fault": fault, "verdict": v, "twins": [str(t) for t in twins], "latent": False,
                "component_ok": g["component_ok"], "mode_ok": g["mode_ok"]}

    def finish(self, trace: dict, extra: dict | None = None) -> None:
        self.trace = trace
        judged = self.judge(trace["diagnosis"], trace["outcome"])
        if trace["outcome"] == "diagnosed":
            self.flow = max(self.flow, 2)
        self.flow = max(self.flow, 3)
        self._advance_flow()
        b = self.bench
        self.emit({
            "type": "done", "mode": self.mode, "bench": "ats", "source": self.source, **judged,
            "outcome": trace["outcome"], "diagnosis": trace["diagnosis"],
            "measurements": trace["measurements"], "redundant": trace["redundant_measurements"],
            "turns": trace["turns"], "tokens": trace["tokens"]["prompt"] + trace["tokens"]["completion"],
            "cost_usd": trace["cost_usd"], "seconds": trace["seconds"],
            "policy_blocked": trace["policy"]["blocked"], "approvals": trace["policy"]["approval_requests"],
            "approvals_denied": trace["policy"]["approvals_denied"],
            "strong_approvals": self.tb.policy.stats.strong_approval_requests if self.tb else 0,
            "recovered_text_calls": trace["recovered_text_calls"], "error": trace["error"],
            "diagnosis_text": diagnosis_text(trace["diagnosis"], trace["outcome"])[0],
            "twins_named": diagnosis_text(trace["diagnosis"], trace["outcome"])[1],
            "panel": snapshot(b, self.flow),
            "truth_live_nets": [n for n in NETLIST.nets if n not in INTERNAL_NETS and b.voltage(n, "NN") > LIVE_V],
            "decisive": None,
            "intervention": True,
            **(extra or {}),
        })
        self.done = True

    def intervene(self, name: str, args: dict) -> None:
        """After the diagnosis: the authorized person isolates, repairs and restores through the same policy."""
        with self._lock:
            if self.cancelled or self.closed or self.tb is None:
                self.emit({"type": "error", "message": self.ended_message()})
                return
            if name not in INTERVENTION_TOOLS:
                self.emit({"type": "error", "message": f"{name} is not an intervention step"})
                return
            self.tb.approver, self.tb.on_event = self.approver, self.on_event
            try:
                self.tb.call(name, args)
            except Cancelled:
                self.emit({"type": "error", "message": self.ended_message()})
                return
            if self.flow == 5:
                self.emit({"type": "verified", "panel": snapshot(self.bench, self.flow),
                           "message": "Transfer verified by the simulator: load on Emergency, position confirmed. "
                                      "UPS countdown stopped."})

    def compare(self, client_fn) -> None:
        """The other diagnosticians on the same fault, side by side with this session. Re-runs start from the same
        scenario state on a fresh bench and use the batch approval rules (approval tier approved, strong approval
        denied); this session's column keeps its live approvals. The agent run is paid and passes the demo spend
        guard; the hybrid (saved transcription, no explanation) and the baseline make no model calls. The engineer
        column is this session if a human ran it, else a recorded engineer trace for this fault, else none."""
        if not self.done or self.trace is None:
            self.emit({"type": "error", "message": "finish the diagnosis first"})
            return
        own = {"manual": "human", "agent": "agent", "hybrid": "hybrid"}[self.mode]
        columns = {own: column(self.trace, self.judge(self.trace["diagnosis"], self.trace["outcome"]),
                               self.tb.policy.stats.strong_approval_requests if self.tb else 0, True)}

        def judged(tr: dict) -> dict:
            return self.judge(tr["diagnosis"], tr["outcome"])

        if own != "human":
            rec = engineer_trace(self.faults)
            columns["human"] = ({**column(rec, judged(rec), 0, True), "engineer": rec.get("engineer"),
                                 "recorded": rec.get("recorded")} if rec else
                                {"runner": "human", "missing": "no engineer trace recorded for this fault"})
        if "baseline" not in columns:
            t0 = time.perf_counter()
            p = AtsInfoGain(_outage(self.faults), NETLIST, model_key="true", approver=approve_standard_only)
            d = p.run()
            tr = make_trace(case="compare_ats", runner="ats_infogain", tb=p.tb, diagnosis=d, outcome=d["outcome"],
                            seconds=time.perf_counter() - t0, notes=p.notes)
            columns["baseline"] = column(tr, judged(tr), p.tb.policy.stats.strong_approval_requests, False)
            self.emit({"type": "compare_progress", "runner": "baseline", "done": True})
        if "hybrid" not in columns:
            try:
                t = transcriptions.load(transcriptions.DEFAULT)
                ok, events = healthy_sequence(to_netlist(t["data"]))
                ready = warm_transcription(t["id"])
                ready.wait()
                r = run_ats_hybrid(_outage(self.faults), None, t["data"], t["raw"], [], flags=t["flags"],
                                   approver=approve_standard_only, repair=False, do_explain=False,
                                   healthy={"ok": ok, "events": events})
                tr = make_trace(case="compare_ats", runner="ats_hybrid", tb=r.planner.tb, diagnosis=r.diagnosis,
                                outcome=r.outcome, seconds=r.seconds, notes=r.planner.notes)
                columns["hybrid"] = {**column(tr, judged(tr), r.planner.tb.policy.stats.strong_approval_requests, False),
                                     "transcription": f"{t['label']} ({t['run_id']})"}
            except Exception as e:  # noqa: BLE001 - one column failing must not lose the others
                columns["hybrid"] = {"runner": "ats_hybrid", "error": f"{type(e).__name__}: {e}"}
            self.emit({"type": "compare_progress", "runner": "hybrid", "done": True})
        if "agent" not in columns and os.environ.get("PROBEFORGE_OFFLINE"):
            columns["agent"] = {"runner": "ats_agent", "missing": "agent not run (offline mode)"}
        if "agent" not in columns:
            try:
                SpendLedger().check(EST_PER_AGENT_RUN_USD, what="an ATS agent run (compare)", demo=True)

                def progress(ev: dict) -> None:
                    if ev["type"] == "turn":
                        self.emit({"type": "compare_progress", "runner": "agent", "turn": ev["turn"]})

                run, tb = run_ats_agent(_outage(self.faults), client_fn(), effort="low", approver=approve_standard_only,
                                        on_event=progress)
                SpendLedger().record(run.cost_usd, "ui ATS compare agent run", demo=True)
                tr = make_trace(case="compare_ats", runner="ats_agent", tb=tb, diagnosis=run.diagnosis,
                                outcome=run.outcome, seconds=run.seconds, run=run)
                columns["agent"] = column(tr, judged(tr), tb.policy.stats.strong_approval_requests, False)
            except Exception as e:  # noqa: BLE001 - spend limit, no key, offline mode, API down
                columns["agent"] = {"runner": "ats_agent", "error": f"{type(e).__name__}: {e}" if not isinstance(
                    e, SpendLimitError) else str(e)}
        fault = self.judge(self.trace["diagnosis"], self.trace["outcome"])["fault"]
        result = {"type": "compare", "bench": "ats", "fault": fault, "columns": columns, "own": own,
                  "note": f"Re-runs use the batch approval rules (approval tier approved, strong approval denied); the "
                          f"{'engineer' if own == 'human' else own} column is this session, with approvals answered live. "
                          "Hybrid v2 runs on the default saved transcription without the explanation call. Times exclude the "
                          "UI display pause."
                          + (" The hybrid and baseline columns are identical here: the model Muse Spark read from the "
                             "drawing behaves like our hand redrawing, so the planner takes the same steps."
                             if columns.get("hybrid", {}).get("sequence") is not None
                             and columns["hybrid"].get("sequence") == columns.get("baseline", {}).get("sequence") else "")}
        COMPARE_DIR.mkdir(parents=True, exist_ok=True)
        (COMPARE_DIR / f"ats_{datetime.now():%Y%m%d_%H%M%S}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        self.emit(result)

    # called from the event loop ---------------------------------------------------

    def answer(self, rid: int, approve: bool) -> None:
        pending = self._pending.get(rid)
        if pending:
            pending[1][0] = bool(approve)
            pending[0].set()

    def cancel(self, notify: bool = True) -> None:
        first = not self.cancelled and not self.closed
        self.cancelled = True
        self.closed = True
        for event, _ in list(self._pending.values()):
            event.set()
        if first and notify:
            self.emit({"type": "stopped", "mode": self.mode, "message": "Session ended"})

    def ended_message(self) -> str:
        return ("This session has ended (End session was pressed). Start a new one." if self.cancelled
                else "This session is finished. Start a new one.")


class Cancelled(Exception):
    pass


class AtsAgentSession(AtsSession):
    mode = "agent"

    def __init__(self, faults, source, case, effort: str, emit, client_fn):
        super().__init__(faults, source, case, emit)
        self.effort = effort
        self.client_fn = client_fn

    def run(self) -> None:
        try:
            SpendLedger().check(EST_PER_AGENT_RUN_USD, what="an ATS agent run", demo=True)
        except SpendLimitError as e:
            self.emit({"type": "error", "message": str(e)})
            self.closed = True
            return
        self.emit({"type": "session", "mode": "agent", "bench": "ats", "source": self.source, "effort": self.effort,
                   "model": MUSE_SPARK, "panel": snapshot(self.bench, self.flow)})
        try:
            run, tb = run_ats_agent(self.bench, self.client_fn(), effort=self.effort, approver=self.approver,
                                    on_event=self.on_event)
        except Exception as e:  # missing key, API down
            if not self.cancelled:
                self.emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            self.closed = True
            return
        self.tb = tb
        SpendLedger().record(run.cost_usd, f"ui ATS agent run ({self.source})", demo=True)
        if self.cancelled or (run.error and "Cancelled" in run.error):
            self.closed = True
            return
        trace = make_trace(case="ui_ats", runner="ats_agent", tb=tb, diagnosis=run.diagnosis, outcome=run.outcome,
                           seconds=run.seconds, run=run)
        self.finish(trace)

    def call(self, name: str, args: dict) -> None:
        if not self.done:
            self.emit({"type": "error", "message": "The agent is diagnosing; the intervention opens after its diagnosis."})
            return
        self.intervene(name, args)


SKIP_IN_REPLAY = ("update_hypotheses", "submit_diagnosis", "get_schematic")


def suggest_next(tb: AtsToolBox) -> dict:
    """Engineer mode, shadow mode: the info-gain planner on our redrawing (the drawing the engineer sees) replays the
    engineer's own executed steps and proposes the next one. It reads only what the engineer observed (the step log and
    whether the switch is isolated), never the bench's injected fault."""
    view = SimpleNamespace(log=tb.log[:1], action_s=tb.action_s, bench=SimpleNamespace(isolated=tb.bench.isolated))
    planner = AtsInfoGain(_outage([]), NETLIST, model_key="true")  # a fault-free bench only to construct the planner
    planner.tb = view
    planner.max_actions = 10**6  # the engineer decides when to stop
    planner.steps = [Step(e["tool"], e["args"], _value(e["tool"], e["result"]), e["step"], 0, 0)
                     for e in tb.log[1:] if e["executed"] and e["tool"] not in SKIP_IN_REPLAY]
    planner._build()
    planner.cands = [c for c in planner.cands if c.faults]  # a fault is present: the switch did not transfer
    plan = planned_next(planner)
    if not planner.cands:
        plan["why"] = "no single fault of our redrawing explains every reading so far"
    return plan


class AtsManualSession(AtsSession):
    """A human engineer drives the same ATS toolbox (same tools, same policy, same step log)."""

    mode = "manual"

    def __init__(self, faults, source, case, engineer: str, emit):
        super().__init__(faults, source, case, emit)
        self.engineer = engineer.strip() or "engineer"
        self.tb = AtsToolBox(self.bench, approver=self.approver, on_event=self.on_event)
        self.started = time.perf_counter()
        self.suggestions: list[dict] = []  # shown only when asked for; the saved trace is then marked assisted

    def suggest(self) -> None:
        with self._lock:
            if self.done or self.cancelled or self.closed:
                self.emit({"type": "error", "message": "Suggestions are for the diagnosis, before you submit it."})
                return
            plan = suggest_next(self.tb)
            terms = [x for x in (terminal_of(p) for p in plan["points"]) if x]
            self.suggestions.append({"after_step": self.tb.step, "tool": plan["tool"], "args": plan["args"]})
            self.emit({"type": "suggestion", "step": self.tb.step, **plan, "terminals": terms})

    def start(self) -> None:
        self.tb.initial_observation()
        self.emit({"type": "session", "mode": "manual", "bench": "ats", "source": self.source, "engineer": self.engineer,
                   "panel": snapshot(self.bench, self.flow)})

    def call(self, name: str, args: dict) -> None:
        if self.done:
            return self.intervene(name, args)
        with self._lock:
            if self.cancelled or self.closed:
                self.emit({"type": "error", "message": self.ended_message()})
                return
            if name not in MANUAL_TOOLS:
                self.emit({"type": "error", "message": f"tool {name!r} is not available in engineer mode"})
                return
            try:
                self.tb.call(name, args)
            except Cancelled:
                self.emit({"type": "error", "message": self.ended_message()})
                return
            if self.tb.diagnosis is not None:
                self._finish_manual()

    def _finish_manual(self) -> None:
        diagnosis = self.tb.diagnosis
        trace = make_trace(case="manual_ats", runner="human", tb=self.tb, diagnosis=diagnosis,
                           outcome=diagnosis.get("outcome", "diagnosed"), seconds=time.perf_counter() - self.started,
                           extra={"engineer": self.engineer, "bench": "ats", "assisted": bool(self.suggestions),
                                  "suggestions": self.suggestions})
        self.finish(trace)
        record = {**trace, "faults": [f.to_dict() for f in self.faults], "source": self.source,
                  "recorded": datetime.now().isoformat(timespec="seconds"), "bench": "ats"}
        ENGINEER_DIR.mkdir(parents=True, exist_ok=True)
        name = "_".join(str(f).replace(":", "-").replace(" ", "-") for f in self.faults)[:80]
        path = ENGINEER_DIR / f"{name}__{self.engineer}__{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        shown = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
        self.emit({"type": "saved", "path": shown})


def terminal_of(point: str) -> str | None:
    """A drawing terminal for a probe point (a terminal, or a net drawn from its first terminal)."""
    if point in NETLIST.terminal_net:
        return point
    return NETLIST.nets[point][0] if point in NETLIST.nets else None


_live: dict = {}
_live_lock = threading.Lock()


class AtsHybridSession(AtsSession):
    """Hybrid v2 on the ATS bench: Read (saved transcription or live re-read), Model (the documented fault-free
    sequence, with the recorded repairs), Plan (info-gain on the transcription, readings on the real bench through the
    same toolbox and policy, approvals answered by the human), Explain. The frozen modules are called, never changed."""

    mode = "hybrid"

    def __init__(self, faults, source, case, transcription: str, emit, client_fn):
        super().__init__(faults, source, case, emit)
        self.transcription = transcription or transcriptions.DEFAULT
        self.client_fn = client_fn
        self.paused_s = 0.0  # UI display pauses, subtracted from every reported time

    def _client(self):
        try:
            return self.client_fn()
        except Exception:  # noqa: BLE001 - no key: the saved model still runs, only the explanation is skipped
            return None

    def live_read(self, client, usage: Usage) -> dict:
        """3 live reads of the drawing crops and the model step (once per server process, then reused)."""
        with _live_lock:
            if "t" not in _live:
                images = sheet_images()
                self.emit({"type": "stage", "text": f"Read: Muse Spark reads the 7 drawing-sheet crops 3 times ({LIVE_READ_TEXT})..."})
                data, flags, summary, raws = read_consensus(client, usage, images, reads=3)
                raw = raws[summary["model_read"] - 1]
                self.emit({"type": "stage", "text": "Model: checking the documented fault-free sequence; Muse Spark repairs "
                                                    "the circuit where it departs..."})
                data, raw, flags, healthy = prepare_model(client, usage, data, raw, flags, images)
                stamp = datetime.now()
                _live["t"] = {"id": "live", "label": "Live re-read", "run_id": "live read in this server process",
                              "recorded": f"{stamp:%Y-%m-%d %H:%M}", "reads": summary["reads"],
                              "repairs": len([a for a in healthy["attempts"] if a.get("accepted")]),
                              "cost_usd": round(usage.cost_usd, 4), "seconds": None, "read_quality": [],
                              "disclosure": "The hybrid pipeline was developed on this one drawing.",
                              "healthy": {k: v for k, v in healthy.items() if k != "versions"}, "flags": flags,
                              "data": data, "raw": raw, "summary": summary}
        return _live["t"]

    def on_update(self, planner, step: int) -> None:
        if self.cancelled:
            raise Cancelled()
        self.tb = planner.tb  # cited evidence on approval cards
        plan = planned_next(planner)
        terms = [x for x in (terminal_of(p) for p in plan["points"]) if x]
        self.emit({"type": "next_step", "step": step, **plan, "terminals": terms})
        if plan["tool"] != "submit_diagnosis" and PLAN_PAUSE_S:
            time.sleep(PLAN_PAUSE_S)
            self.paused_s += PLAN_PAUSE_S

    def run(self) -> None:
        live = self.transcription == "live"
        if live and not live_read_available():
            self.emit({"type": "error", "message": "A live re-read needs the drawing crops on this machine "
                                                   "(scripts/render_ats_sheets.py); use a saved transcription."})
            self.closed = True
            return
        try:
            SpendLedger().check(EST_HYBRID_LIVE_USD if live else EST_HYBRID_SAVED_USD, what="an ATS hybrid run", demo=True)
            t = None if live else transcriptions.load(self.transcription)
        except (SpendLimitError, KeyError) as e:
            self.emit({"type": "error", "message": str(e)})
            self.closed = True
            return
        self.emit({"type": "session", "mode": "hybrid", "bench": "ats", "source": self.source, "model": MUSE_SPARK,
                   "panel": snapshot(self.bench, self.flow)})
        usage = Usage(effort="medium")
        client = self._client()
        try:
            if live:
                if client is None:
                    raise RuntimeError("no Meta API key: a live re-read is not possible")
                t = self.live_read(client, usage)
            self.emit({"type": "ats_transcription", **{k: t.get(k) for k in ("id", "label", "run_id", "recorded", "reads",
                       "repairs", "cost_usd", "seconds", "read_quality", "disclosure")},
                       "attempts": t["healthy"].get("attempts", []), "where": t["healthy"].get("where", []),
                       "stopped": t["healthy"].get("stopped"), "flags": len(t["flags"]),
                       "components": len(t["data"].get("components") or {}), "nets": len(t["data"].get("nets") or {})})
            ok, events = healthy_sequence(to_netlist(t["data"]))
            self.emit({"type": "model_check", "ok": ok, "events": events, "expected": HEALTHY_EVENTS})
            if ok:
                if live:
                    warm(t["data"], t["flags"])
                else:
                    ready = warm_transcription(t["id"])
                    if not ready.is_set():
                        self.emit({"type": "stage", "text": "Simulating every candidate fault of the transcription (once "
                                                            "per transcription, about 80 s)..."})
                        while not ready.wait(0.5):
                            if self.cancelled:
                                raise Cancelled()
            self.emit({"type": "stage_done"})
            images = sheet_images() if live_read_available() else []
            result = run_ats_hybrid(self.bench, client, t["data"], t["raw"], images, usage=usage, flags=t["flags"],
                                    approver=self.approver, repair=bool(client and images), do_explain=client is not None,
                                    on_event=self.on_event, on_update=self.on_update, healthy={"ok": ok, "events": events})
        except Cancelled:
            SpendLedger().record(usage.cost_usd, f"ui ATS hybrid run ({self.source}, ended)", demo=True)
            self.closed = True
            return
        except Exception as e:  # noqa: BLE001 - API down, unusable transcription
            SpendLedger().record(usage.cost_usd, f"ui ATS hybrid run ({self.source}, failed)", demo=True)
            if not self.cancelled:
                self.emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            self.closed = True
            return
        SpendLedger().record(usage.cost_usd, f"ui ATS hybrid run ({self.source})", demo=True)
        self.tb = result.planner.tb
        if self.cancelled:
            self.closed = True
            return
        trace = make_trace(case="ui_ats", runner="ats_hybrid", tb=self.tb, diagnosis=result.diagnosis,
                           outcome=result.outcome, seconds=max(result.seconds - self.paused_s, 0.0), run=usage,
                           notes=result.planner.notes,
                           extra={"explanation": result.explanation, "corrections": result.corrections,
                                  "transcription": t["id"]})
        self.finish(trace, extra={
            "explanation": result.explanation,
            "transcription": f"{t['label']} ({t['run_id']}, recorded {t['recorded']})",
            "corrections": [{"step": 0, "diff": c.get("diff", []), "explanation": c.get("explanation", ""),
                             "error": c.get("error"), "rejected": c.get("rejected"), "reasons": []}
                            for c in result.corrections],
            "gave_up": result.planner.gave_up,
            "wiring_check": None,
            "display_pause_s": self.paused_s,
        })

    def call(self, name: str, args: dict) -> None:
        if not self.done:
            self.emit({"type": "error", "message": "The pipeline is diagnosing; the intervention opens after its diagnosis."})
            return
        self.intervene(name, args)


def start_session(action: str, msg: dict, emit, client_fn) -> AtsSession:
    faults, source, case = pick(msg)
    warm_signatures()
    if action == "start":
        return AtsAgentSession(faults, source, case, msg.get("effort") or "low", emit, client_fn)
    if action == "start_manual":
        return AtsManualSession(faults, source, case, str(msg.get("engineer") or ""), emit)
    if action == "start_hybrid":
        return AtsHybridSession(faults, source, case, str(msg.get("schematic") or ""), emit, client_fn)
    raise ValueError(f"unknown action {action!r}")
