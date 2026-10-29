"""Web backend: live agent sessions and manual (human engineer) sessions over one WebSocket.

The browser never receives the injected fault while a session runs: tool events carry
what the actor saw (the same results the agent gets), panel snapshots carry what an
operator sees on the front panel. The fault, its observational twins and the true live
wiring are sent only in the final "done" event.

Protocol (JSON over /ws):
  client -> server  {"action": "start", "source": "scenario" | "random", "scenario": "s01",
                     "effort": "low", "include_latent": false, "fault": optional test hook}
                    {"action": "start_manual", ... same fault choice ..., "engineer": "name"}
                    {"action": "start_hybrid", ... same fault choice ..., "schematic": "saved" | "live"}
                    {"action": "flags", "id": 1, "approve": true}        (confirm flagged transcription regions)
                    {"action": "wiring", "id": 1, "choice": 0 | null}   (which wiring of a flagged region is real)
                    {"action": "tool", "name": "measure_voltage", "args": {...}}      (manual mode)
                    {"action": "approval", "id": 1, "approve": true}
                    {"action": "compare"}                                           (after a manual run)
                    {"action": "stop"}
  server -> client  session, turn, tool, hypotheses, approval_request, approval_answer, done,
                    stopped (the user ended the session), saved, compare_progress, compare, error;
                    hybrid also: stage, transcription, flags_request, flags_answer, conflict, correction,
                    correction_rejected, wiring_check, wiring_request, wiring_answer
"""

import asyncio
import itertools
import json
import random
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from probeforge.agent.client import MUSE_SPARK, make_client
from probeforge.agent.loop import run_agent
from probeforge.baseline import HalfSplitBaseline
from probeforge.eval.spend import EST_PER_AGENT_RUN_USD, SpendLedger, SpendLimitError
from probeforge.eval.trace import decisive_measurement, make_trace, summary, verdict
from probeforge.faults import Fault
from probeforge.faults.catalog import SCENARIOS_DIR, all_faults, load_scenarios
from probeforge.faults.model import COMPONENT_MODES, PART_MODES
from probeforge.hybrid import read_consensus, run_hybrid
from probeforge.hybrid.llm import Usage
from probeforge.hybrid.netlist_io import flags_of, wrong_nets
from probeforge.sim import Circuit, Netlist
from probeforge.sim.schematic import render_png, render_svg
from probeforge.tools import ApprovalRequest, ToolBox, deny_all

ROOT = Path(__file__).resolve().parents[3]
CIRCUIT_PATH = SCENARIOS_DIR / "circuits" / "star_delta_reversing.yaml"
ENGINEER_DIR = SCENARIOS_DIR / "engineer_traces"
COMPARE_DIR = ROOT / "runs" / "compare"
NETLIST = Netlist.load(CIRCUIT_PATH)
SVG = render_svg(NETLIST)
SCENARIOS = {s.id: s for s in load_scenarios()}
LIVE_V = 20.0
APPROVAL_TIMEOUT_S = 600
MANUAL_TOOLS = {"read_indicators", "press_button", "wait", "set_power", "measure_voltage", "measure_resistance",
                "perform_action", "submit_diagnosis"}

app = FastAPI(title="ProbeForge")
_client = None


def client():
    global _client
    if _client is None:
        _client = make_client()
    return _client


def ledger() -> SpendLedger:
    return SpendLedger()


class Cancelled(Exception):
    pass


@app.get("/api/meta")
def meta() -> dict:
    return {
        "model": MUSE_SPARK,
        "title": NETLIST.title,
        "neutral": NETLIST.neutral,
        # symptom only: the scenario title would name the fault
        "scenarios": [{"id": s.id, "symptom": s.symptom} for s in SCENARIOS.values()],
        "buttons": [{"id": c.id, "label": c.label} for c in NETLIST.components_of("button")],
        "lamps": [{"id": c.id, "label": c.label} for c in NETLIST.components_of("lamp")],
        "components": [
            {
                "id": c.id, "type": c.type, "label": c.label,
                "modes": list(COMPONENT_MODES.get(c.type, ())),
                "parts": [{"name": p.name, "kind": p.kind, "modes": list(PART_MODES[p.kind])} for p in c.parts],
            }
            for c in NETLIST.components.values()
        ],
        "thermal_relays": [c.id for c in NETLIST.components_of("thermal_relay")],
    }


@app.get("/api/schematic")
def schematic() -> Response:
    return Response(SVG, media_type="image/svg+xml")


def panel_snapshot(circuit: Circuit) -> dict:
    ind = circuit.indicators()
    return {
        "lamps": ind["lamps"],
        "motor": ind["motor"],
        "line_currents": ind["phase_currents"],
        "line_currents_a": ind["line_currents_a"],
        "power": circuit.power,
        "time_s": round(circuit.time, 1),
    }


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-") or "x"


class Session:
    """Shared by agent and manual sessions: one faulty circuit, approvals, enriched tool events."""

    mode = "agent"

    def __init__(self, fault: Fault, source: str, emit):
        self.fault = fault
        self.source = source
        self.emit = emit
        self.circuit = Circuit(NETLIST)
        self.circuit.apply_fault(fault)
        self.circuit.set_power(True)
        self.cancelled = False
        self.done = False
        self.trace: dict | None = None
        self.judged: dict = {}
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple[threading.Event, list]] = {}

    # called from worker threads ------------------------------------------------

    def approver(self, req: ApprovalRequest) -> bool:
        rid = next(self._ids)
        event, answer = threading.Event(), [False]
        self._pending[rid] = (event, answer)
        self.emit({"type": "approval_request", "id": rid, "step": req.step, "tool": req.tool,
                   "args": {k: v for k, v in req.args.items() if k not in ("button_role",)},
                   "policy_reason": req.policy_reason, "agent_reason": req.agent_reason})
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
            ev = {**ev, "probes": self._probes(ev), "panel": panel_snapshot(self.circuit)}
        self.emit(ev)

    def _probes(self, ev: dict) -> list[dict]:
        r = ev["result"]
        readings = []
        if ev["tool"] == "measure_voltage" and "volts" in r:
            readings.append(("V", r["point_a"], r["point_b"], r["volts"]))
        elif ev["tool"] == "measure_resistance" and "ohms" in r:
            readings.append(("R", r["point_a"], r["point_b"], r["ohms"]))
        elif ev["tool"] == "press_button":
            readings += [("V", x["point_a"], x["point_b"], x["volts"]) for x in r.get("readings", [])]
        out = []
        for kind, a, b, value in readings:
            na, nb = self.circuit.net_of(a), self.circuit.net_of(b)
            out.append({
                "kind": kind, "a": a, "b": b, "value": value, "net_a": na, "net_b": nb,
                "term_a": a if a in NETLIST.terminal_net else NETLIST.nets[na][0],
                "term_b": b if b in NETLIST.terminal_net else NETLIST.nets[nb][0],
            })
        return out

    def finish(self, trace: dict, extra: dict | None = None) -> None:
        self.trace = trace
        self.judged = verdict(NETLIST, str(CIRCUIT_PATH), self.fault, trace["diagnosis"], trace["outcome"])
        self.emit({
            "type": "done", "mode": self.mode, "source": self.source,
            "fault": str(self.fault), **self.judged,
            "outcome": trace["outcome"], "diagnosis": trace["diagnosis"],
            "measurements": trace["measurements"], "redundant": trace["redundant_measurements"],
            "turns": trace["turns"], "tokens": trace["tokens"]["prompt"] + trace["tokens"]["completion"],
            "cost_usd": trace["cost_usd"], "seconds": trace["seconds"],
            "policy_blocked": trace["policy"]["blocked"], "approvals": trace["policy"]["approval_requests"],
            "approvals_denied": trace["policy"]["approvals_denied"],
            "recovered_text_calls": trace["recovered_text_calls"], "error": trace["error"],
            "panel": panel_snapshot(self.circuit),
            "truth_live_nets": [n for n, v in self.circuit.net_voltages().items() if v > LIVE_V],
            "decisive": decisive_measurement(trace["tool_log"], trace["hypotheses_history"], trace["diagnosis"], NETLIST),
            **(extra or {}),
        })
        self.done = True

    # called from the event loop -------------------------------------------------

    def answer(self, rid: int, approve: bool) -> None:
        pending = self._pending.get(rid)
        if pending:
            pending[1][0] = bool(approve)
            pending[0].set()

    def cancel(self, notify: bool = True) -> None:
        """End the session. notify: tell the browser ("stopped"); off when a new session replaces this one,
        because the browser has already reset for the new session."""
        first = not self.cancelled and not self.done
        self.cancelled = True
        for event, _ in list(self._pending.values()):
            event.set()
        if first and notify:
            self.emit({"type": "stopped", "mode": self.mode, "message": "Session ended"})

    def ended_message(self) -> str:
        return ("This session has ended (End session was pressed). Start a new one." if self.cancelled
                else "This session is finished. Start a new one.")


class AgentSession(Session):
    mode = "agent"

    def __init__(self, fault: Fault, source: str, effort: str, emit):
        super().__init__(fault, source, emit)
        self.effort = effort

    def run(self) -> None:
        try:
            ledger().check(EST_PER_AGENT_RUN_USD, what="an agent run", demo=True)
        except SpendLimitError as e:
            self.emit({"type": "error", "message": str(e)})
            self.done = True
            return
        self.emit({"type": "session", "mode": "agent", "source": self.source, "effort": self.effort,
                   "model": MUSE_SPARK, "panel": panel_snapshot(self.circuit)})
        try:
            run, tb = run_agent(self.circuit, client(), effort=self.effort, approver=self.approver,
                                on_event=self.on_event)
        except Exception as e:  # missing key, API down
            if not self.cancelled:
                self.emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            self.done = True
            return
        ledger().record(run.cost_usd, f"ui agent run ({self.source})", demo=True)
        if self.cancelled or (run.error and "Cancelled" in run.error):
            self.done = True  # the browser already got "stopped" (or a new session replaced this one)
            return
        trace = make_trace(case="ui", runner="agent", tb=tb, diagnosis=run.diagnosis, outcome=run.outcome,
                           seconds=run.seconds, run=run)
        self.finish(trace)


TRANSCRIPTIONS = {
    # real Muse Spark transcriptions with known crossover errors (6 of 35 nets), kept for repeatable demos:
    # (netlist, image the repair step sees; None = the rendered schematic)
    "saved": (SCENARIOS_DIR / "transcriptions" / "star_delta_run2.yaml", None),
    "photo": (SCENARIOS_DIR / "transcriptions" / "star_delta_photo_run3.yaml", SCENARIOS_DIR / "photos" / "star_delta_phone.jpg"),
}
_live_read: dict = {}  # one live transcription per server process (about a minute and $0.07 each)
_live_lock = threading.Lock()


class HybridSession(Session):
    """Read (transcribe), Model, Plan (info-gain on the transcription), Verify (repair), Explain."""

    mode = "hybrid"

    def __init__(self, fault: Fault, source: str, schematic: str, emit):
        super().__init__(fault, source, emit)
        self.schematic = schematic if schematic in ("live", *TRANSCRIPTIONS) else "saved"

    def confirm_flags(self, flags: list[dict]) -> bool:
        """Human confirmation of the regions the transcription flagged (same wait as an approval)."""
        rid = next(self._ids)
        event, answer = threading.Event(), [False]
        self._pending[rid] = (event, answer)
        self.emit({"type": "flags_request", "id": rid, "flags": flags})
        event.wait(APPROVAL_TIMEOUT_S)
        self._pending.pop(rid, None)
        if self.cancelled:
            raise Cancelled()
        self.emit({"type": "flags_answer", "id": rid, "accepted": answer[0]})
        return answer[0]

    def confirm_wiring(self, request: dict) -> int | None:
        """The diagnosis depends on a flagged region: the human says which wiring the panel really has."""
        rid = next(self._ids)
        event, answer = threading.Event(), [None]
        self._pending[rid] = (event, answer)
        self.emit({"type": "wiring_request", "id": rid, **request})
        event.wait(APPROVAL_TIMEOUT_S)
        self._pending.pop(rid, None)
        if self.cancelled:
            raise Cancelled()
        self.emit({"type": "wiring_answer", "id": rid, "choice": answer[0]})
        return answer[0]

    def choose(self, rid: int, choice) -> None:
        pending = self._pending.get(rid)
        if pending:
            pending[1][0] = choice if isinstance(choice, int) else None
            pending[0].set()

    def read(self, usage: Usage) -> tuple[dict, list[dict], str, bytes]:
        if self.schematic != "live":
            path, image = TRANSCRIPTIONS[self.schematic]
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            png = image.read_bytes() if image else render_png(NETLIST)
            return data, flags_of(data), f"saved Muse Spark transcription ({path.name})", png
        png = render_png(NETLIST)
        with _live_lock:
            if "data" not in _live_read:
                self.emit({"type": "stage", "stage": "read",
                           "text": "Muse Spark is reading the schematic image 3 times (disagreements become uncertain regions)..."})
                data, flags, info = read_consensus(client(), usage, png)
                how = (f"live Muse Spark transcription, {info['reads']} reads, model from read {info['model_read']}, "
                       f"{info['disagreement_regions']} regions where the reads disagree")
                _live_read.update(data=data, flags=flags, how=how, at=datetime.now().strftime("%H:%M"))
                return data, flags, how, png
        return (_live_read["data"], _live_read["flags"], f"{_live_read['how']} (read at {_live_read['at']}, reused)", png)

    def on_update(self, planner, entry: dict) -> None:
        if self.cancelled:
            raise Cancelled()
        counts: dict = {}
        for c in planner.cands:
            counts[c.fault] = counts.get(c.fault, 0) + 1
        total = sum(counts.values()) or 1
        hyps = [{"component": f.component, "part": f.part or "", "failure_mode": f.mode, "probability": k / total,
                 "reason": f"{len(counts)} candidate faults consistent with every reading"}
                for f, k in sorted(counts.items(), key=lambda x: -x[1])[:12]]
        self.emit({"type": "hypotheses", "step": entry["step"], "hypotheses": hyps})

    def run(self) -> None:
        try:
            ledger().check(EST_PER_AGENT_RUN_USD, what="a hybrid run", demo=True)
        except SpendLimitError as e:
            self.emit({"type": "error", "message": str(e)})
            self.done = True
            return
        self.emit({"type": "session", "mode": "hybrid", "source": self.source, "model": MUSE_SPARK,
                   "panel": panel_snapshot(self.circuit)})
        usage = Usage(effort="medium")
        try:
            data, flags, how, png = self.read(usage)
            self.emit({"type": "transcription", "how": how, "flags": flags,
                       "components": len(data.get("components") or {}), "nets": len(data.get("nets") or {})})
            if flags and not self.confirm_flags(flags):
                self.emit({"type": "error", "message": "transcription not confirmed: correct the flagged regions first"})
                self.done = True
                return
            result = run_hybrid(self.circuit, client(), data, png, usage=usage, flags=flags,
                                on_event=self.on_event, on_update=self.on_update, confirm_wiring=self.confirm_wiring)
        except Cancelled:
            ledger().record(usage.cost_usd, f"ui hybrid run ({self.source}, ended)", demo=True)
            self.done = True  # the browser already got "stopped" (or a new session replaced this one)
            return
        except Exception as e:  # missing key, API down, unusable transcription
            ledger().record(usage.cost_usd, f"ui hybrid run ({self.source}, failed)", demo=True)
            if not self.cancelled:
                self.emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            self.done = True
            return
        ledger().record(usage.cost_usd, f"ui hybrid run ({self.source})", demo=True)
        trace = make_trace(case="ui", runner="hybrid", tb=result.planner.tb, diagnosis=result.diagnosis,
                           outcome=result.outcome, seconds=result.seconds, run=usage, notes=result.planner.notes,
                           extra=result.trace_extra())
        self.finish(trace, extra={
            "explanation": result.explanation, "cited_steps": result.cited_steps, "transcription": how,
            "transcription_wrong_nets": len(wrong_nets(data, NETLIST)),  # revealed with the fault, after the run
            "corrections": [{"step": c["step"], "diff": c.get("diff", []), "explanation": c.get("explanation", ""),
                             "error": c.get("error"), "rejected": c.get("rejected"), "reasons": c.get("reasons", [])}
                            for c in result.corrections],
            "gave_up": result.planner.gave_up,
            "wiring_check": result.wiring_check,
        })


class ManualSession(Session):
    """A human engineer drives the same ToolBox (same tools, same policy, same step log)."""

    mode = "manual"

    def __init__(self, fault: Fault, source: str, engineer: str, emit):
        super().__init__(fault, source, emit)
        self.engineer = engineer.strip() or "engineer"
        self.tb = ToolBox(self.circuit, approver=self.approver, on_event=self.on_event)
        self.started = time.perf_counter()
        self.saved_path: Path | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self.tb.initial_observation()
        self.emit({"type": "session", "mode": "manual", "source": self.source, "engineer": self.engineer,
                   "panel": panel_snapshot(self.circuit)})

    def call(self, name: str, args: dict) -> None:
        with self._lock:
            if self.done or self.cancelled:  # never drop a call silently
                self.emit({"type": "error", "message": self.ended_message()})
                return
            if name not in MANUAL_TOOLS:
                self.emit({"type": "error", "message": f"tool {name!r} is not available in manual mode"})
                return
            try:
                self.tb.call(name, args)
            except Cancelled:
                self.emit({"type": "error", "message": self.ended_message()})
                return
            if self.tb.diagnosis is not None and not self.done:
                self._finish_manual()

    def _finish_manual(self) -> None:
        seconds = time.perf_counter() - self.started
        diagnosis = self.tb.diagnosis
        trace = make_trace(case="manual", runner="human", tb=self.tb, diagnosis=diagnosis,
                           outcome=diagnosis.get("outcome", "diagnosed"), seconds=seconds,
                           extra={"engineer": self.engineer})
        self.finish(trace)
        record = {
            **trace,
            # engineer reference traces name the fault: no agent ever reads this folder
            "fault": self.fault.to_dict(), "fault_text": str(self.fault), "source": self.source,
            "verdict": self.judged["verdict"], "recorded": datetime.now().isoformat(timespec="seconds"),
            "circuit": CIRCUIT_PATH.relative_to(SCENARIOS_DIR).as_posix(),
        }
        ENGINEER_DIR.mkdir(parents=True, exist_ok=True)
        path = ENGINEER_DIR / f"{slug(str(self.fault))}__{slug(self.engineer)}__{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        self.saved_path = path
        shown = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
        self.emit({"type": "saved", "path": shown})

    def compare(self) -> None:
        """Run the baseline and the agent on the same fault; send human / agent / baseline side by side."""
        if not self.done or self.trace is None:
            self.emit({"type": "error", "message": "finish the manual diagnosis first"})
            return
        columns = {"human": summary(self.trace, self.judged)}

        c = Circuit(NETLIST)
        c.apply_fault(self.fault)
        c.set_power(True)
        t0 = time.perf_counter()
        b = HalfSplitBaseline(c)
        b_diag = b.run()
        b_trace = make_trace(case="compare", runner="baseline", tb=b.tb, diagnosis=b_diag,
                             outcome=b_diag.get("outcome"), seconds=time.perf_counter() - t0, notes=b.notes)
        columns["baseline"] = summary(b_trace, verdict(NETLIST, str(CIRCUIT_PATH), self.fault, b_diag, b_trace["outcome"]))
        self.emit({"type": "compare_progress", "runner": "baseline", "done": True})

        try:
            ledger().check(EST_PER_AGENT_RUN_USD, what="an agent run", demo=True)
            c = Circuit(NETLIST)
            c.apply_fault(self.fault)
            c.set_power(True)

            def progress(ev: dict) -> None:
                if ev["type"] == "turn":
                    self.emit({"type": "compare_progress", "runner": "agent", "turn": ev["turn"]})

            run, tb = run_agent(c, client(), effort="low", approver=deny_all, on_event=progress)
            ledger().record(run.cost_usd, "ui compare agent run", demo=True)
            a_trace = make_trace(case="compare", runner="agent", tb=tb, diagnosis=run.diagnosis, outcome=run.outcome,
                                 seconds=run.seconds, run=run)
            columns["agent"] = summary(a_trace, verdict(NETLIST, str(CIRCUIT_PATH), self.fault, run.diagnosis, run.outcome))
        except SpendLimitError as e:
            columns["agent"] = {"runner": "agent", "error": str(e)}
        except Exception as e:
            columns["agent"] = {"runner": "agent", "error": f"{type(e).__name__}: {e}"}

        result = {"type": "compare", "fault": str(self.fault), "columns": columns,
                  "note": "the agent runs with approvals denied (batch rules); the human's approvals were answered live"}
        COMPARE_DIR.mkdir(parents=True, exist_ok=True)
        stem = self.saved_path.stem if self.saved_path else f"{slug(str(self.fault))}_{datetime.now():%H%M%S}"
        (COMPARE_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        self.emit(result)


def parse_fault(text: str) -> Fault:
    """'QF1:5-6 open' or 'KM3 welded' -> Fault (must be one of the catalog faults)."""
    target, _, mode = text.strip().partition(" ")
    comp, _, part = target.partition(":")
    fault = Fault(comp, mode.strip(), part or None)
    if fault not in all_faults(NETLIST):
        raise ValueError(f"unknown fault {text!r}")
    return fault


def clean_pool() -> list[Fault]:
    data = yaml.safe_load((SCENARIOS_DIR / "holdout_clean.yaml").read_text(encoding="utf-8"))
    return [Fault.from_dict(c) for c in data["cases"]]


def pick_fault(msg: dict) -> tuple[Fault, str]:
    """The fault and the pool it came from (the pool is shown with the result)."""
    if msg.get("fault"):  # test / demo hook (?fault= in the URL), never offered in the UI
        return parse_fault(msg["fault"]), "fault chosen by URL"
    source = msg.get("source")
    if source == "scenario":
        sc = SCENARIOS[msg["scenario"]]
        return sc.fault, f"scenario {sc.id}"
    if source == "clean":
        pool = clean_pool()
        return random.SystemRandom().choice(pool), f"clean test fault (holdout_clean.yaml, {len(pool)})"
    faults = all_faults(NETLIST)
    return random.SystemRandom().choice(faults), f"random fault (any of {len(faults)})"


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(ev: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    async def sender() -> None:
        while True:
            await websocket.send_json(await queue.get())

    def background(fn, *args) -> None:
        """Run a blocking job in a worker thread; a crash reaches the browser as an error event."""
        def job():
            try:
                fn(*args)
            except Exception as e:  # noqa: BLE001 - report anything, the session must not hang silently
                emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
        loop.run_in_executor(None, job)

    sender_task = asyncio.create_task(sender())
    session: Session | None = None
    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            if action in ("start", "start_manual", "start_hybrid"):
                if session and not session.done:
                    session.cancel(notify=False)
                try:
                    fault, source = pick_fault(msg)
                except (ValueError, KeyError) as e:
                    emit({"type": "error", "message": str(e)})
                    continue
                if action == "start":
                    session = AgentSession(fault, source, msg.get("effort") or "low", emit)
                    background(session.run)
                elif action == "start_hybrid":
                    session = HybridSession(fault, source, str(msg.get("schematic") or "saved"), emit)
                    background(session.run)
                else:
                    session = ManualSession(fault, source, str(msg.get("engineer") or ""), emit)
                    session.start()
            elif action == "tool" and isinstance(session, ManualSession):
                args = msg.get("args") if isinstance(msg.get("args"), dict) else {}
                background(session.call, str(msg.get("name")), args)
            elif action == "tool":
                emit({"type": "error", "message": "No engineer session is running: choose Engineer, pick a fault and press Start."})
            elif action == "compare" and isinstance(session, ManualSession):
                background(session.compare)
            elif action in ("approval", "flags") and session:
                session.answer(int(msg["id"]), bool(msg.get("approve")))
            elif action == "wiring" and isinstance(session, HybridSession):
                session.choose(int(msg["id"]), msg.get("choice"))
            elif action == "stop" and session:
                session.cancel()
            elif action == "stop":
                emit({"type": "error", "message": "No session is running."})
    except WebSocketDisconnect:
        if session:
            session.cancel(notify=False)
    finally:
        sender_task.cancel()


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
