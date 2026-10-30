"""ATS bench sessions for the web backend (agent and engineer), on the same WebSocket as the relay panel.

As for the relay panel, the browser never receives the injected fault while a session runs: tool events carry what
the actor saw, panel snapshots what a technician at the switch sees (the controller face, the sources, the load, the
UPS, the mechanism position flag). The fault, its observational twins and the true live nets are sent only in "done".

After the diagnosis the session stays open for the authorized intervention (isolate, repair, restore) through the
same toolbox and policy; the UPS status flow ends at "Transfer verified" only when the simulator confirms the load on
Emergency with the position confirmed by the controller.
"""

import itertools
import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path

import yaml

from probeforge.agent.client import MUSE_SPARK
from probeforge.ats.agent import run_ats_agent
from probeforge.ats.ambiguity import signature
from probeforge.ats.bench import INTERNAL_NETS, REPAIR_KINDS, AtsBench
from probeforge.ats.faults import COMPONENT_MODES, PART_MODES, all_faults, validate
from probeforge.ats.policy import RULES
from probeforge.ats.tools import AtsApprovalRequest, AtsToolBox
from probeforge.eval.scoring import grade
from probeforge.eval.spend import EST_PER_AGENT_RUN_USD, SpendLedger, SpendLimitError
from probeforge.eval.trace import make_trace
from probeforge.faults.model import Fault
from probeforge.sim.schematic import render_svg

ROOT = Path(__file__).resolve().parents[3]
CASES_DIR = ROOT / "scenarios" / "ats"
ENGINEER_DIR = ROOT / "scenarios" / "engineer_traces" / "ats"
BENCH = AtsBench()
NETLIST = BENCH.n
SVG = render_svg(NETLIST)
OUTAGE_S = 60.0  # every session starts 60 s after the Normal source failed (as the batch runs)
LIVE_V = 20.0
APPROVAL_TIMEOUT_S = 600
FLOW = ["Fault detected", "Diagnosis in progress", "Root cause identified", "Awaiting authorized intervention",
        "Power restored", "Transfer verified"]
MANUAL_TOOLS = {"read_panel", "read_event_log", "read_metering", "wait", "measure_voltage", "measure_resistance",
                "isolate_sources", "restore_sources", "manual_operation_check", "repeat_transfer_attempt",
                "perform_action", "submit_diagnosis"}
INTERVENTION_TOOLS = MANUAL_TOOLS - {"submit_diagnosis"}  # after the diagnosis, for the authorized person


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


def meta() -> dict:
    warm_signatures()  # the browser asks for meta when the ATS bench is chosen: precompute the pool and twins then
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

    def finish(self, trace: dict) -> None:
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
            "panel": snapshot(b, self.flow),
            "truth_live_nets": [n for n in NETLIST.nets if n not in INTERNAL_NETS and b.voltage(n, "NN") > LIVE_V],
            "decisive": None,
            "intervention": True,
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


class AtsManualSession(AtsSession):
    """A human engineer drives the same ATS toolbox (same tools, same policy, same step log)."""

    mode = "manual"

    def __init__(self, faults, source, case, engineer: str, emit):
        super().__init__(faults, source, case, emit)
        self.engineer = engineer.strip() or "engineer"
        self.tb = AtsToolBox(self.bench, approver=self.approver, on_event=self.on_event)
        self.started = time.perf_counter()

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
                           extra={"engineer": self.engineer, "bench": "ats"})
        self.finish(trace)
        record = {**trace, "faults": [f.to_dict() for f in self.faults], "source": self.source,
                  "recorded": datetime.now().isoformat(timespec="seconds"), "bench": "ats"}
        ENGINEER_DIR.mkdir(parents=True, exist_ok=True)
        name = "_".join(str(f).replace(":", "-").replace(" ", "-") for f in self.faults)[:80]
        path = ENGINEER_DIR / f"{name}__{self.engineer}__{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        shown = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
        self.emit({"type": "saved", "path": shown})


def start_session(action: str, msg: dict, emit, client_fn) -> AtsSession:
    faults, source, case = pick(msg)
    warm_signatures()
    if action == "start":
        return AtsAgentSession(faults, source, case, msg.get("effort") or "low", emit, client_fn)
    if action == "start_manual":
        return AtsManualSession(faults, source, case, str(msg.get("engineer") or ""), emit)
    raise ValueError("the hybrid pipeline is not available on the ATS bench")
