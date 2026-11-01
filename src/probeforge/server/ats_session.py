"""ATS web sessions: the shared session (one bench, approvals with cited readings, enriched tool events, the
result, the authorized intervention, Compare)."""

import itertools
import json
import os
import threading
import time
from datetime import datetime

from probeforge.ats.agent import run_ats_agent
from probeforge.ats import transcriptions
from probeforge.ats.ambiguity import signature
from probeforge.ats.bench import INTERNAL_NETS
from probeforge.ats.hybrid.pipeline import healthy_sequence, run_ats_hybrid
from probeforge.ats.hybrid.read import to_netlist
from probeforge.ats.infogain import AtsInfoGain
from probeforge.ats.tools import AtsApprovalRequest, AtsToolBox, approve_standard_only
from probeforge.eval.scoring import grade
from probeforge.eval.spend import EST_PER_AGENT_RUN_USD, SpendLimitError
from probeforge.eval.trace import make_trace
from probeforge.faults.model import Fault
from probeforge.server import ats_common as common
from probeforge.server.ats_common import APPROVAL_TIMEOUT_S, INTERVENTION_TOOLS, LIVE_V, NETLIST, _f, _outage
from probeforge.server.names import prune
from probeforge.server.ats_views import column, describe, diagnosis_text, engineer_trace, snapshot

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
        self.seen: dict[int, dict] = {}  # every tool step of this session, for the citations on approval cards
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
        # citations come from the steps seen so far: the agent session gets its toolbox only after the run
        log = {**self.seen, **{e["step"]: e for e in (self.tb.log if self.tb else [])}}
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
            self.seen[ev["step"]] = ev
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
        twins = [f for f, s in common.catalog_signatures().items() if s == sig and f not in answers]
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
            "type": "done", "mode": self.mode, "bench": "ats", **judged,
            "source": f"{self.source} ({self.case['id']})" if self.case else self.source,  # the case name with the result
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
            "ups_at_diagnosis": trace.get("ups_at_diagnosis"),
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
                ready = common.warm_transcription(t["id"])
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
                common.ledger().check(EST_PER_AGENT_RUN_USD, what="an ATS agent run (compare)", demo=True)

                def progress(ev: dict) -> None:
                    if ev["type"] == "turn":
                        self.emit({"type": "compare_progress", "runner": "agent", "turn": ev["turn"]})

                run, tb = run_ats_agent(_outage(self.faults), common.metered(client_fn(), "ui ATS compare agent run"),
                                        effort="low", approver=approve_standard_only,
                                        on_event=progress)
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
        common.COMPARE_DIR.mkdir(parents=True, exist_ok=True)
        (common.COMPARE_DIR / f"ats_{datetime.now():%Y%m%d_%H%M%S}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        prune(common.COMPARE_DIR)
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
