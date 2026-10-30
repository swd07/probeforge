"""Information-gain planner on the ATS bench: the ceiling baseline on the true netlist, and the planner of Hybrid v2
on a transcribed netlist.

Candidates are faults of a MODEL netlist (the true one for the baseline, a transcription for the hybrid), each
simulated on its own bench from the same scenario state as the real switch (the Normal source failed 60 s earlier).
Every reading is taken on the REAL bench through the same toolbox and policy as the agent, then replayed on every
candidate bench (so virtual time, the UPS and the controller sequence stay in step); candidates whose reading differs
are dropped. The next reading is the one whose predicted outcomes split the remaining candidates best (entropy).

Phases follow the policy: live readings (voltages, the position indicator) first; when they no longer split the
candidates, isolation is requested (approval tier; strong approval if it would drop a powered load, which batch runs
deny) and the planner continues with resistances and the manual operation check. It never repeats a transfer (strong
approval). Honest note, as for the relay panel: this needs a complete, exact fault model; the catalog is extended with
the documented compound fault of the coil burnout chain (both cut-off contacts of one side not opening, with or without
the coil they burnt), labelled as an assumption in docs/ATS_MODEL.md.

Hybrid v2 hooks: wiring variants (alternative models from flagged regions, joint fault x wiring candidates), a conflict
hook (a reading no candidate explains: the repair step may return a corrected model, the planner rebuilds and replays)
and an update hook for the UI.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from probeforge.ats.bench import INTERNAL_NETS, AtsBench
from probeforge.ats.faults import all_faults
from probeforge.ats.tools import AtsToolBox, approve_standard_only
from probeforge.faults.model import Fault
from probeforge.sim.netlist import Netlist
from probeforge.tools import approve_all

OUTAGE_S = 60.0
MAX_ACTIONS = 25
COIL = ("TS", "A-B")


def fault_model(n: Netlist) -> list[tuple[Fault, ...]]:
    """Single catalog faults plus the documented compound faults: both cut-off contacts of one side stuck closed (one
    misadjusted cut-off setting), alone or with the coil they burnt. () is the fault-free candidate."""
    singles = [(f,) for f in all_faults(n)]
    compounds = []
    ts = n.components.get("TS")
    if ts:
        for kind in ("cutoff_n", "cutoff_e"):
            parts = [p.name for p in ts.parts if p.kind == kind]
            if len(parts) == 2:
                pair = tuple(Fault("TS", "stuck_closed", p) for p in parts)
                compounds.append(pair)
                if any(p.kind == "solenoid" for p in ts.parts):
                    compounds.append(pair + (Fault("TS", "burnt", ts.parts[[p.kind for p in ts.parts].index("solenoid")].name),))
    return [()] + singles + compounds


def root_of(faults: tuple[Fault, ...]) -> Fault | None:
    """The root cause of a candidate: its first fault (a burnt coil after a cut-off fault is the consequence)."""
    return faults[0] if faults else None


@dataclass
class Cand:
    faults: tuple[Fault, ...]
    variant: int
    bench: AtsBench
    tb: AtsToolBox

    @property
    def root(self) -> Fault | None:
        return root_of(self.faults)


@dataclass
class Step:
    tool: str
    args: dict
    value: object
    step: int
    before: int
    after: int


def _value(tool: str, result: dict):
    """The comparable outcome of a tool result (what the reading says, not its step number or time)."""
    if "error" in result:
        return ("error", result["error"])
    if tool == "measure_voltage":
        return result["volts"]
    if tool == "measure_resistance":
        return result["ohms"]
    if tool == "read_position_indicator":
        return result["position_indicator"]
    if tool == "manual_operation_check":
        rs = result.get("readings_at_other_position") or result.get("readings") or []
        return (result["moved_to_other_position"], tuple(r["ohms"] for r in rs))
    if tool in ("isolate_sources",):
        return (result.get("load_powered"), result.get("display"))
    return None


def observation(tb: AtsToolBox) -> tuple:
    """The step 0 observation as a comparable tuple (panel, events, metering)."""
    o = tb.log[0]["result"]
    return (tuple(sorted(o["lights"].items())), o["display"], tuple(o["alarms"]), o["generator"], o["load_powered"],
            o["ups"]["draining"], tuple(o["metering"]["Normal"]), tuple(o["metering"]["Emergency"]),
            tuple((e["event"], e["cause"]) for e in o["events"]))


_base_cache: dict[tuple, list] = {}


def _scenario_benches(n: Netlist, key) -> list[tuple[tuple[Fault, ...], AtsBench]]:
    """Every candidate of a model at the scenario start (cached per model: the same for every case)."""
    if key not in _base_cache:
        out = []
        for fs in fault_model(n):
            b = AtsBench(netlist=n, faults=list(fs))
            b.lose_utility()
            b.step(OUTAGE_S)
            out.append((fs, b))
        _base_cache[key] = out
    return _base_cache[key]


def _fingerprint(n: Netlist) -> tuple:
    """A model netlist by content (parts and nets), so the scenario benches are reused across cases."""
    return (tuple(sorted((p.id, p.kind) for p in n.parts.values())), tuple(sorted(tuple(sorted(v)) for v in n.nets.values())))


def _entropy(groups: dict) -> float:
    total = sum(len(v) for v in groups.values())
    return -sum(len(v) / total * math.log2(len(v) / total) for v in groups.values() if v)


class AtsInfoGain:
    def __init__(self, bench: AtsBench, model: Netlist, *, approver=approve_standard_only, variants: list[Netlist] | None = None,
                 on_event: Callable | None = None, on_update: Callable | None = None, on_conflict: Callable | None = None,
                 max_actions: int = MAX_ACTIONS, model_key=None):
        self.tb = AtsToolBox(bench, approver=approver, on_event=on_event)
        self.models = [model, *(variants or [])]
        self.model_key = model_key
        self.on_update, self.on_conflict = on_update, on_conflict
        self.max_actions = max_actions
        self.steps: list[Step] = []
        self.notes: list[str] = []
        self.corrections: list[dict] = []
        self.gave_up = False
        self.cands: list[Cand] = []

    # ------------------------------------------------------------ candidates

    def _build(self) -> None:
        """Candidates for every model variant, replayed through every action taken so far."""
        self.cands = []
        obs = observation(self.tb)
        for vi, n in enumerate(self.models):
            key = (self.model_key, vi) if self.model_key is not None else ("nets", _fingerprint(n))
            for fs, base in _scenario_benches(n, key):
                b = base.clone()
                tb = AtsToolBox(b, approver=approve_all, action_s=self.tb.action_s)
                tb.initial_observation()
                if observation(tb) != obs:
                    continue
                c = Cand(fs, vi, b, tb)
                if all(self._replay(c, s) for s in self.steps):
                    self.cands.append(c)

    def _replay(self, c: Cand, s: Step) -> bool:
        c.tb.step = s.step - 1  # keep step numbers aligned with the real toolbox (cited evidence steps)
        return _value(s.tool, c.tb.call(s.tool, s.args)) == s.value

    @property
    def faults_left(self) -> list[tuple[Fault, ...]]:
        seen = []
        for c in self.cands:
            if c.faults not in seen:
                seen.append(c.faults)
        return seen

    # ------------------------------------------------------------ actions

    def _probe_points(self, n: Netlist) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        acc = lambda t: n.terminal_net[t] not in INTERNAL_NETS  # noqa: E731
        across = [(p.a, p.b) for p in n.parts.values() if p.a != p.b and acc(p.a) and acc(p.b)]
        to_n = [(n.nets[k][0], "NN") for k in n.nets if k not in INTERNAL_NETS and k != "NN"]
        return across, to_n

    def _predict(self, c: Cand, tool: str, args: dict):
        b = c.bench
        try:
            if tool == "measure_voltage":
                return b.voltage(args["point_a"], args["point_b"])
            if tool == "measure_resistance":
                r = b.resistance(args["point_a"], args["point_b"])
                return "open" if r == math.inf else r
            if tool == "read_position_indicator":
                return "moving" if b.moving else {"N": "Normal", "E": "Emergency"}[b.position]
            if tool == "manual_operation_check":
                if id(c) not in self._far:
                    x = b.clone()
                    self._far[id(c)] = (x.manual_operate(), x)
                moved, x = self._far[id(c)]
                r = [x.resistance(p["point_a"], p["point_b"]) for p in args["readings"]]
                return (moved, tuple("open" if v == math.inf else v for v in r))
        except (KeyError, ValueError):  # a probe point the variant does not have
            return ("error",)
        return None

    def _menu(self, live: bool) -> list[tuple[str, dict]]:
        across, to_n = self._probe_points(self.models[0])
        if live:
            return [("read_position_indicator", {})] + [("measure_voltage", {"point_a": a, "point_b": b}) for a, b in across + to_n]
        menu = [("measure_resistance", {"point_a": a, "point_b": b}) for a, b in across]
        menu += [("manual_operation_check", {"readings": [{"point_a": a, "point_b": b}], "reason": "check whether the mechanism "
                  "moves and how the contacts read at the other position"}) for a, b in across]
        return menu

    def _best(self, live: bool) -> tuple[tuple[str, dict] | None, float]:
        best, gain = None, 0.0
        self._far: dict = {}  # each candidate operated to the other position, once per choice
        done = {(s.tool, repr(s.args)) for s in self.steps}
        roots = {c.root for c in self.cands}
        if len(roots) <= 1:
            return None, 0.0
        for tool, args in self._menu(live):
            if (tool, repr(args)) in done:
                continue
            groups: dict = {}
            for c in self.cands:
                groups.setdefault(self._predict(c, tool, args), set()).add(c.root)
            if len(groups) < 2:
                continue
            # split the root causes (not the wiring variants of one root cause)
            sizes = {k: v for k, v in groups.items()}
            g = _entropy(sizes) - (0.01 if tool == "manual_operation_check" else 0.0)
            if g > gain + 1e-9:
                best, gain = (tool, args), g
        return best, gain

    # ------------------------------------------------------------ run

    def _take(self, tool: str, args: dict) -> bool:
        before = len(self.cands)
        result = self.tb.call(tool, args)
        if not self.tb.log[-1]["executed"]:
            self.notes.append(f"step {result['step']}: {tool} not executed ({result.get('error', '')})")
            return False
        s = Step(tool, args, _value(tool, result), result["step"], before, 0)
        self.steps.append(s)
        self.cands = [c for c in self.cands if self._replay(c, s)]
        s.after = len(self.cands)
        if not self.cands and self.on_conflict:
            self._conflict(s)
        self._update(s.step)
        return True

    def _conflict(self, s: Step) -> None:
        """No candidate explains the readings: ask the conflict hook for a corrected model, rebuild and replay."""
        new = self.on_conflict({"planner": self, "step": s})
        if new is not None:
            self.models = new if isinstance(new, list) else [new]
            self.model_key = None
            self._build()

    def _update(self, step: int) -> None:
        counts: dict = {}
        for c in self.cands:
            counts[c.root] = counts.get(c.root, 0) + 1
        total = sum(counts.values()) or 1
        hyps = [{"component": f.component if f else "none", "part": (f.part or "") if f else "",
                 "failure_mode": f.mode if f else "open", "probability": round(k / total, 3),
                 "reason": f"{len(counts)} root causes consistent with every reading"}
                for f, k in sorted(counts.items(), key=lambda x: -x[1])[:10] if f]
        if hyps:
            self.tb.call("update_hypotheses", {"hypotheses": hyps})
        if self.on_update:
            self.on_update(self, step)

    def run(self) -> dict:
        self.tb.initial_observation()
        self._build()
        if not self.cands and self.on_conflict:
            self._conflict(Step("initial observation", {}, None, 0, 0, 0))
        self._update(0)
        live = True
        while len(self.steps) < self.max_actions and len({c.root for c in self.cands}) > 1:
            choice, gain = self._best(live)
            if choice is None and live:
                live = False
                if not self.tb.bench.isolated:
                    ev = [s.step for s in self.steps if isinstance(s.value, float)][-1:]
                    if not self._take("isolate_sources", {"reason": "resistance checks and a manual operation check: live "
                                      "readings no longer separate the remaining causes", "evidence_steps": ev}):
                        break
                continue
            if choice is None:
                break
            if not self._take(*choice):
                break
        return self.submit()

    def submit(self) -> dict:
        roots = []
        for c in self.cands:
            if c.root not in roots:
                roots.append(c.root)
        evidence = [{"step": s.step, "type": "instrument_reading" if s.tool in ("measure_voltage", "measure_resistance",
                     "manual_operation_check") else "functional_test",
                     "observation": f"{s.tool} {s.args.get('point_a', '')} {s.args.get('point_b', '')}: {s.value}".strip()}
                    for s in self.steps if s.after < s.before][-4:]
        evidence = [{"step": 0, "type": "functional_test", "observation": "controller panel, event log and metering"}] + evidence
        same_part = len({(f.component, f.part) for f in roots if f}) == 1 and None not in roots
        if len(roots) == 1 and roots[0] is not None or (roots and same_part):
            f = roots[0]
            args = {"outcome": "diagnosed", "component": f.component, "part": f.part or "", "failure_mode": f.mode,
                    "confidence": round(1 / len(roots), 2), "evidence": evidence}
            if len(roots) > 1:
                args["note"] = "no reading separates: " + ", ".join(str(r) for r in roots)
        else:
            self.gave_up = not self.cands
            args = {"outcome": "insufficient_information", "confidence": 0.0, "evidence": evidence[:1],
                    "note": ("no candidate explains every reading" if not self.cands else
                             "still possible: " + ", ".join(str(r) if r else "no fault" for r in roots[:8]))}
        self.tb.call("submit_diagnosis", args)
        return args
