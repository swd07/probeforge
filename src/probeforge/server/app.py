"""Web backend: runs one live diagnosis session per WebSocket and streams every step.

The browser never receives the injected fault while the session runs: tool events
carry what the agent saw (the same results the agent got), panel snapshots carry
what an operator sees on the front panel. The fault, its observational twins and
the true live wiring are sent only in the final "done" event.

Protocol (JSON over /ws):
  client -> server  {"action": "start", "source": "scenario" | "random", "scenario": "s01",
                     "effort": "low", "include_latent": false}
                    {"action": "approval", "id": 1, "approve": true}
                    {"action": "stop"}
  server -> client  session, turn, tool, hypotheses, approval_request, approval_answer, done, error
"""

import asyncio
import itertools
import random
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from probeforge.agent.client import MUSE_SPARK, make_client
from probeforge.agent.loop import run_agent
from probeforge.eval.ambiguity import justified, observational_twins
from probeforge.eval.scoring import score
from probeforge.faults import Fault
from probeforge.faults.catalog import SCENARIOS_DIR, all_faults, has_visible_symptom, load_scenarios
from probeforge.sim import Circuit, Netlist
from probeforge.sim.schematic import render_svg
from probeforge.tools import ApprovalRequest

ROOT = Path(__file__).resolve().parents[3]
CIRCUIT_PATH = SCENARIOS_DIR / "circuits" / "star_delta_reversing.yaml"
NETLIST = Netlist.load(CIRCUIT_PATH)
SVG = render_svg(NETLIST)
SCENARIOS = {s.id: s for s in load_scenarios()}
LIVE_V = 20.0
APPROVAL_TIMEOUT_S = 600

app = FastAPI(title="ProbeForge")
_client = None


def client():
    global _client
    if _client is None:
        _client = make_client()
    return _client


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


class Session:
    def __init__(self, fault: Fault, source: str, effort: str, emit):
        self.fault = fault
        self.source = source
        self.effort = effort
        self.emit = emit
        self.circuit = Circuit(NETLIST)
        self.circuit.apply_fault(fault)
        self.circuit.set_power(True)
        self.cancelled = False
        self.done = False
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple[threading.Event, list]] = {}

    # called from the agent thread -------------------------------------------

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

    def run(self) -> None:
        self.emit({"type": "session", "source": self.source, "effort": self.effort, "model": MUSE_SPARK,
                   "panel": panel_snapshot(self.circuit)})
        try:
            run, tb = run_agent(self.circuit, client(), effort=self.effort, approver=self.approver,
                                on_event=self.on_event)
        except Exception as e:  # missing key, API down
            self.emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            self.done = True
            return
        if self.cancelled or run.error and "Cancelled" in run.error:
            self.emit({"type": "error", "message": "session stopped"})
            self.done = True
            return
        s = score(run.diagnosis, self.fault)
        latent = not has_visible_symptom(NETLIST, self.fault)
        correct = (s["component_ok"] and s["mode_ok"]) or (latent and run.outcome == "insufficient_information")
        twins = observational_twins(str(CIRCUIT_PATH), self.fault)
        just = justified(run.diagnosis, self.fault, twins, correct)
        verdict = "correct" if correct else "justified" if just else (
            "no diagnosis" if run.outcome != "diagnosed" else "wrong")
        self.emit({
            "type": "done",
            "fault": str(self.fault), "latent": latent, "twins": [str(t) for t in twins],
            "outcome": run.outcome, "diagnosis": run.diagnosis, "verdict": verdict, **s,
            "measurements": tb.measurements, "redundant": tb.redundant_measurements,
            "turns": run.turns, "tokens": run.prompt_tokens + run.completion_tokens, "cost_usd": run.cost_usd,
            "seconds": run.seconds, "policy_blocked": tb.policy.stats.blocked,
            "approvals": tb.policy.stats.approval_requests, "approvals_denied": tb.policy.stats.approvals_denied,
            "recovered_text_calls": run.recovered_text_calls, "error": run.error,
            "panel": panel_snapshot(self.circuit),
            "truth_live_nets": [n for n, v in self.circuit.net_voltages().items() if v > LIVE_V],
        })
        self.done = True

    # called from the event loop ---------------------------------------------

    def answer(self, rid: int, approve: bool) -> None:
        pending = self._pending.get(rid)
        if pending:
            pending[1][0] = bool(approve)
            pending[0].set()

    def cancel(self) -> None:
        self.cancelled = True
        for event, _ in list(self._pending.values()):
            event.set()


def parse_fault(text: str) -> Fault:
    """'QF1:5-6 open' or 'KM3 welded' -> Fault (must be one of the catalog faults)."""
    target, _, mode = text.strip().partition(" ")
    comp, _, part = target.partition(":")
    fault = Fault(comp, mode.strip(), part or None)
    if fault not in all_faults(NETLIST):
        raise ValueError(f"unknown fault {text!r}")
    return fault


def pick_fault(msg: dict) -> tuple[Fault, str]:
    if msg.get("fault"):  # test / demo hook (?fault= in the URL), never offered in the UI
        return parse_fault(msg["fault"]), "fault chosen by URL"
    if msg.get("source") == "scenario":
        sc = SCENARIOS[msg["scenario"]]
        return sc.fault, f"scenario {sc.id}"
    faults = all_faults(NETLIST)
    if not msg.get("include_latent"):
        faults = [f for f in faults if has_visible_symptom(NETLIST, f)]
    return random.SystemRandom().choice(faults), "random unseen fault"


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

    sender_task = asyncio.create_task(sender())
    session: Session | None = None
    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            if action == "start":
                if session and not session.done:
                    session.cancel()
                try:
                    fault, source = pick_fault(msg)
                except (ValueError, KeyError) as e:
                    emit({"type": "error", "message": str(e)})
                    continue
                session = Session(fault, source, msg.get("effort") or "low", emit)
                loop.run_in_executor(None, session.run)
            elif action == "approval" and session:
                session.answer(int(msg["id"]), bool(msg.get("approve")))
            elif action == "stop" and session:
                session.cancel()
    except WebSocketDisconnect:
        if session:
            session.cancel()
    finally:
        sender_task.cancel()


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
