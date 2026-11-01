"""ATS web sessions: the agent, Engineer and Hybrid v2 sessions, and start_session."""

import json
import threading
import time
from datetime import datetime
from types import SimpleNamespace

from probeforge.agent.client import MUSE_SPARK
from probeforge.ats.agent import run_ats_agent
from probeforge.ats import transcriptions
from probeforge.ats.hybrid.pipeline import HEALTHY_EVENTS, healthy_sequence, prepare_model, run_ats_hybrid, warm
from probeforge.ats.hybrid.read import read_consensus, sheet_images, to_netlist
from probeforge.ats.infogain import AtsInfoGain, Step, _value
from probeforge.ats.nextstep import planned_next
from probeforge.ats.tools import AtsToolBox
from probeforge.eval.spend import EST_PER_AGENT_RUN_USD, SpendLimitError
from probeforge.eval.trace import make_trace
from probeforge.hybrid.llm import Usage
from probeforge.server import ats_common as common
from probeforge.server import settings
from probeforge.server.ats_common import (EST_HYBRID_LIVE_USD, EST_HYBRID_SAVED_USD, LIVE_READ_TEXT, MANUAL_TOOLS, NETLIST,
                                          ROOT, _outage, live_read_available)
from probeforge.server.ats_session import AtsSession, Cancelled
from probeforge.server.ats_views import snapshot, terminal_of

class AtsAgentSession(AtsSession):
    mode = "agent"

    def __init__(self, faults, source, case, effort: str, emit, client_fn):
        super().__init__(faults, source, case, emit)
        self.effort = effort
        self.client_fn = client_fn

    def run(self) -> None:
        try:
            common.ledger().check(EST_PER_AGENT_RUN_USD, what="an ATS agent run", demo=True)
        except SpendLimitError as e:
            self.emit({"type": "error", "message": str(e)})
            self.closed = True
            return
        self.emit({"type": "session", "mode": "agent", "bench": "ats", "source": self.source, "effort": self.effort,
                   "model": MUSE_SPARK, "panel": snapshot(self.bench, self.flow)})
        try:
            run, tb = run_ats_agent(self.bench, common.metered(self.client_fn(), f"ui ATS agent run ({self.source})"),
                                    effort=self.effort, approver=self.approver, on_event=self.on_event)
        except Exception as e:  # missing key, API down
            if not self.cancelled:
                self.emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            self.closed = True
            return
        self.tb = tb
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
        common.ENGINEER_DIR.mkdir(parents=True, exist_ok=True)
        name = "_".join(str(f).replace(":", "-").replace(" ", "-") for f in self.faults)[:80]
        path = common.ENGINEER_DIR / f"{name}__{self.engineer}__{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        shown = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
        self.emit({"type": "saved", "path": shown})




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
            return common.metered(self.client_fn(), f"ui ATS hybrid run ({self.source})")
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
        if plan["tool"] != "submit_diagnosis" and common.PLAN_PAUSE_S:
            time.sleep(common.PLAN_PAUSE_S)
            self.paused_s += common.PLAN_PAUSE_S

    def run(self) -> None:
        live = self.transcription == "live"
        if live and (settings.PUBLIC or not live_read_available()):
            self.emit({"type": "error", "message": "A live re-read needs the drawing crops on this machine "
                                                   "(scripts/render_ats_sheets.py); use a saved transcription."})
            self.closed = True
            return
        try:
            common.ledger().check(EST_HYBRID_LIVE_USD if live else EST_HYBRID_SAVED_USD, what="an ATS hybrid run", demo=True)
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
                    ready = common.warm_transcription(t["id"])
                    if not ready.is_set():
                        self.emit({"type": "stage", "text": "Simulating every candidate fault of the transcription (once "
                                                            "per transcription, about 80 s)..."})
                        while not ready.wait(0.5):
                            if self.cancelled:
                                raise Cancelled()
            self.emit({"type": "stage_done"})
            # repairs need the drawing crops; a public host has none, and the per-call token cap would cut them
            images = sheet_images() if live_read_available() and not settings.PUBLIC else []
            result = run_ats_hybrid(self.bench, client, t["data"], t["raw"], images, usage=usage, flags=t["flags"],
                                    approver=self.approver, repair=bool(client and images), do_explain=client is not None,
                                    on_event=self.on_event, on_update=self.on_update, healthy={"ok": ok, "events": events})
        except Cancelled:
            self.closed = True
            return
        except Exception as e:  # noqa: BLE001 - API down, unusable transcription
            if not self.cancelled:
                self.emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            self.closed = True
            return
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
    from probeforge.server.ats import pick  # the front module (meta, pick)

    faults, source, case = pick(msg)
    common.warm_signatures()
    if action == "start":
        return AtsAgentSession(faults, source, case, msg.get("effort") or "low", emit, client_fn)
    if action == "start_manual":
        return AtsManualSession(faults, source, case, str(msg.get("engineer") or ""), emit)
    if action == "start_hybrid":
        return AtsHybridSession(faults, source, case, str(msg.get("schematic") or ""), emit, client_fn)
    raise ValueError(f"unknown action {action!r}")
