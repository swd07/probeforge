"""Information-gain planner.

It keeps every single fault the model netlist can have as a candidate (generated from the netlist:
each part in each failure mode), simulates each candidate in lock step with the real panel, and at
every step takes the action whose predicted outcomes split the surviving candidates best (smallest
expected number of survivors). Readings that a candidate does not reproduce eliminate it.

As a baseline (InfoGainBaseline with no model netlist) the model is the true netlist. That is not
a fair peer of the agent: it needs a complete and exact fault model of this very circuit, which
the agent does not have. It shows how far measurement choice alone can go with perfect knowledge.

In the hybrid pipeline the model is a netlist transcribed from the schematic image, while the
readings still come from the true circuit through the ToolBox. When a reading is inconsistent with
every remaining candidate, the model itself must be wrong (or the fault is outside the single-fault
catalog): the planner calls on_conflict, which may return a corrected netlist. The planner then
rebuilds the candidates from the corrected netlist, replays every action taken so far against
the recorded readings, and continues. on_conflict may also reject its own proposal (returns no
netlist and a record with "rejected"); that counts as an attempt and the planner asks again. A
review callback sees the draft diagnosis before it is submitted and may change it.

Joint hypotheses (hybrid only, with a variant_source): a candidate is (fault, unknown parameters,
wiring variant), where variant 0 is the model netlist and the others are alternative wirings of the
regions the transcription flagged as uncertain. Variants are added when they matter and only if they
reproduce every reading so far:
- as soon as the surviving faults are one component in one failure mode and their parts lie in a
  flagged region (before any decision to switch the power off, which cannot be undone): that region's
  alternative wirings, with the surviving faults and the same component's faults of the same mode. The planner then keeps
  measuring (counting distinct faults, not candidates, so it does not spend readings on wiring that
  does not change the answer) and may also measure across a part's own two terminals, at rest or while
  a button is held: such a reading does not depend on how the rest of the circuit is wired. A specific
  part is reported only when one remains.
- on a conflict, before any correction is requested: every flagged region, one component's pins at a
  time, with the faults alive before the conflict and the faults of that component.
After MAX_REJECTED rejected correction proposals in a run, no more proposals are requested.

It uses the same ToolBox and policy as the agent: voltage only live, resistance only dead, at most
3 consecutive start presses, and it never re-applies power (that would need approval after a trip).
Probe points are terminal ids, which the drawing and the panel share (net names are the model's own).
"""

import copy
import itertools
from collections.abc import Callable
from typing import NamedTuple

from probeforge.faults.catalog import all_faults
from probeforge.faults.model import Fault
from probeforge.sim import Circuit, CircuitError, Netlist
from probeforge.tools.toolbox import Approver, ToolBox, deny_all

HOLD_S = 0.2
WAIT_S = 7.0
MAX_STEPS = 60
MAX_CORRECTIONS = 3
MAX_REJECTED = 2
# values a drawing usually does not print, by component type; with a param_grid the planner treats
# each missing one as unknown and keeps a candidate per grid value (log-spaced, not tuned to this circuit)
PARAM_KEYS = {"timer": "delay", "thermal_relay": "trip_time"}
DEFAULT_PARAM_GRID = {"delay": (1.0, 3.0, 10.0, 30.0), "trip_time": (3.0, 10.0, 30.0)}


class Cand(NamedTuple):
    """A candidate: one fault, a value for every parameter the model netlist does not know, and the
    wiring variant it is simulated on (0: the model netlist)."""

    fault: Fault
    params: tuple = ()  # (("KT.delay", 3.0), ...)
    variant: int = 0

    def __str__(self) -> str:
        return (str(self.fault) + (" [" + ", ".join(f"{k}={v:g}" for k, v in self.params) + "]" if self.params else "")
                + (f" [wiring {self.variant}]" if self.variant else ""))


class Variant(NamedTuple):
    """An alternative wiring of a flagged region, as offered by a variant_source."""

    label: str
    components: tuple  # the components whose pins were re-assigned
    netlist: Netlist
    region: tuple  # terminals of the flagged region(s) it comes from
    data: dict | None = None  # the netlist as a dict (for showing the wiring to a human)


def _net_key(netlist: Netlist) -> frozenset:
    return frozenset(frozenset(terms) for terms in netlist.nets.values())


def _q(x):
    """Readings compared at 3 significant figures: different netlists build different solver matrices."""
    if isinstance(x, float):
        return float(f"{x:.3g}")
    if isinstance(x, (tuple, list)):
        return tuple(_q(v) for v in x)
    return x


def _lamps(lamps: dict) -> tuple:
    return tuple(sorted((k.strip().lower(), v) for k, v in lamps.items()))


def _view(c: Circuit, amps: bool = True) -> tuple:
    """Panel as compared. amps=False (motor rating unknown): line currents only as zero/nominal/overcurrent."""
    ind = c.indicators()
    return (_lamps(ind["lamps"]), ind["motor"], tuple(sorted(ind["phase_currents"].items())),
            _q(tuple(sorted(ind["line_currents_a"].items()))) if amps else (), c.power)


def _result_view(r: dict, amps: bool = True) -> tuple:
    return (_lamps(r["lamps"]), r["motor"], tuple(sorted(r["line_currents"].items())),
            _q(tuple(sorted(r["line_currents_a"].items()))) if amps else (), r["power_switch"] == "on")


def _ohms(v: float):
    return "open" if v == float("inf") else _q(v)


def simulate(c: Circuit, name: str, args: dict, amps: bool = True):
    """Predicted outcome of one tool call on a candidate circuit (state-changing calls mutate c)."""
    if name == "read_indicators":
        return _view(c, amps)
    if name == "measure_voltage":
        return _q(c.voltage(args["point_a"], args["point_b"]))
    if name == "measure_resistance":
        return _ohms(c.resistance(args["point_a"], args["point_b"]))
    if name == "press_button":
        c.hold(args["button"])
        c.step(args.get("hold_seconds", HOLD_S))
        held = _view(c, amps)
        volts = tuple(_q(c.voltage(m["point_a"], m["point_b"])) for m in args.get("measure_while_held", []))
        c.release(args["button"])
        return held, volts, _view(c, amps)
    if name == "wait":
        c.step(args["seconds"])
        return _view(c, amps)
    if name == "set_power":
        c.set_power(args["on"])
        return _view(c, amps)
    raise ValueError(f"cannot simulate {name}")


def observed(name: str, r: dict, amps: bool = True):
    """The outcome actually read from the ToolBox, in the same shape as simulate()."""
    if name == "measure_voltage":
        return _q(r["volts"])
    if name == "measure_resistance":
        return "open" if r["ohms"] == "open" else _q(r["ohms"])
    if name == "press_button":
        return (_result_view(r["while_held"], amps), tuple(_q(x["volts"]) for x in r.get("readings", [])),
                _result_view(r["after_release"], amps))
    return _result_view(r, amps)


def with_params(netlist: Netlist, params: tuple) -> Netlist:
    """A copy of the netlist with some component parameters set (("KT.delay", 3.0), ...)."""
    if not params:
        return netlist
    n = copy.copy(netlist)
    n.components = dict(netlist.components)
    for key, value in params:
        cid, name = key.split(".")
        comp = copy.copy(n.components[cid])
        comp.params = {**comp.params, name: value}
        n.components[cid] = comp
    return n


STATEFUL = {"press_button", "wait", "set_power"}
# a candidate whose simulation cannot settle (relay chatter, uncleared short) predicts this, so any real
# reading eliminates it; a transcribed netlist can make such circuits
UNSTABLE = "simulation did not settle"


def run_actions(netlist: Netlist, params: tuple, fault: Fault | None, actions: list[tuple[str, dict]],
                power0: bool, amps: bool) -> list:
    """Predicted outcome of each action, in order, on one circuit (UNSTABLE from the step it fails on)."""
    out = []
    try:
        c = Circuit(with_params(netlist, params))
        if fault is not None:
            c.apply_fault(fault)
        c.set_power(power0)
        for name, args in actions:
            out.append(simulate(c, name, args, amps))
    except (CircuitError, KeyError, ValueError):
        pass
    return out + [UNSTABLE] * (len(actions) - len(out))


def consistent(netlist: Netlist, cands: list[Cand], history: list[dict], power0: bool, amps: bool) -> list[Cand]:
    """The candidates that reproduce every recorded reading on this netlist."""
    actions = [(e["tool"], e["args"]) for e in history]
    return [cand for cand in cands
            if run_actions(netlist, cand.params, cand.fault, actions, power0, amps) == [e["actual"] for e in history]]


class InfoGainBaseline:
    def __init__(self, circuit: Circuit, approver: Approver = deny_all, candidates: list[Fault] | None = None,
                 model: Netlist | None = None, on_conflict: Callable[[dict], tuple] | None = None,
                 on_event: Callable[[dict], None] | None = None, max_corrections: int = MAX_CORRECTIONS,
                 on_update: Callable[["InfoGainBaseline", dict], None] | None = None,
                 param_grid: dict[str, tuple] | None = None,
                 review: Callable[["InfoGainBaseline", dict], dict] | None = None,
                 variant_source: Callable[[set | None], list[Variant]] | None = None):
        self.tb = ToolBox(circuit, approver=approver, on_event=on_event)
        self.on_event = on_event
        self.power0 = circuit.power
        self.on_conflict = on_conflict
        self.on_update = on_update  # called after every recorded reading (the UI shows the candidates)
        self.review = review
        self.variant_source = variant_source
        self.variant_resolved = 0  # conflicts explained by a wiring variant without a correction
        self.max_corrections = max_corrections
        self.history: list[dict] = []  # executed tool calls with the observed outcome
        self.corrections: list[dict] = []
        self.gave_up = False
        self.conflicts = 0  # readings that contradicted every candidate
        self.consecutive_starts = 0
        self.evidence: list[dict] = []
        self.notes: list[str] = []
        self._fixed_candidates = candidates
        self.param_grid = param_grid
        self.set_model(model or circuit.netlist)

    # ---------------------------------------------------------------- model

    def set_model(self, netlist: Netlist) -> dict | None:
        """Use this netlist as the model: fresh candidates, replayed against every recorded reading.
        Returns the history entry at which the candidates ran out (None if some survive)."""
        self.n = netlist
        self.models: list[Netlist] = [netlist]  # wiring variants; index = Cand.variant
        self.variants: list[Variant | None] = [None]
        self._model_keys = {_net_key(netlist)}
        self._expanded: set = set()
        self.wiring_region: set[str] = set()  # flagged terminals the diagnosis was checked against
        self.neutral = netlist.nets[netlist.neutral][0]
        buttons = netlist.components_of("button")
        self.stop = next((b.id for b in buttons if b.label.lower().startswith("stop")), None)
        self.starts = [b.id for b in buttons if b.label.lower().startswith("start")]
        self.buttons = [b.id for b in buttons]
        self.points = [terms[0] for net, terms in netlist.nets.items() if net != netlist.neutral and terms]
        self.parts = list(netlist.parts.values())
        self.amps = all("rated_current" in m.params for m in netlist.components_of("motor"))
        self.unknown = [f"{c.id}.{PARAM_KEYS[c.type]}" for c in netlist.components.values()
                        if self.param_grid and PARAM_KEYS.get(c.type) in self.param_grid
                        and PARAM_KEYS[c.type] not in c.params]
        grids = [[(k, v) for v in self.param_grid[k.split(".")[1]]] for k in self.unknown]
        self.assignments = [tuple(a) for a in itertools.product(*grids)]
        variants = {a: with_params(netlist, a) for a in self.assignments}
        faults = self._fixed_candidates if netlist is self.tb.circuit.netlist and self._fixed_candidates else all_faults(netlist)
        self.cands: dict[Cand, Circuit] = {}
        self.unstable = 0  # candidates dropped because their circuit never settles
        for f in faults:
            for a in self.assignments:
                try:
                    c = Circuit(variants[a])
                    c.apply_fault(f)
                    c.set_power(self.power0)
                except CircuitError:
                    self.unstable += 1
                    continue
                self.cands[Cand(f, a)] = c
        self.last_pred: dict = {}
        for entry in self.history:
            if not self._apply(entry, self._predict(entry["tool"], entry["args"])):
                return entry
        return None

    def healthy_outcomes(self) -> list:
        """What a fault-free circuit of the current model reads for every recorded action (unknown
        parameters taken from a surviving candidate)."""
        params = next(iter(self.cands)).params if self.cands else self.assignments[0]
        return run_actions(self.n, params, None, [(e["tool"], e["args"]) for e in self.history], self.power0, self.amps)

    @property
    def faults_left(self) -> list[Fault]:
        return list(dict.fromkeys(c.fault for c in self.cands))

    @property
    def joint(self) -> bool:
        return len(self.models) > 1

    # ---------------------------------------------------------------- joint hypotheses

    def _replayed(self, cand: Cand) -> Circuit | None:
        """The candidate's circuit after every recorded action, or None if it misses a reading."""
        try:
            c = Circuit(with_params(self.models[cand.variant], cand.params))
            c.apply_fault(cand.fault)
            c.set_power(self.power0)
            for e in self.history:
                if simulate(c, e["tool"], e["args"], self.amps) != e["actual"]:
                    return None
        except (CircuitError, KeyError, ValueError):
            return None
        return c

    def _expand(self, terminals: set | None, faults_for: Callable[[Variant], list[Fault]], params: list[tuple]) -> int:
        """Add the wiring variants offered for these terminals (None: every flagged region, one component at a
        time) with the given faults and parameter values; keep the candidates that fit every reading."""
        # around given terminals: once per model; every flagged region (a conflict): once per reading
        key = frozenset(terminals) if terminals is not None else ("conflict", len(self.history))
        if not self.variant_source or key in self._expanded:
            return 0
        self._expanded.add(key)
        added = 0
        for v in self.variant_source(terminals):
            nk = _net_key(v.netlist)
            if nk in self._model_keys:
                continue
            self._model_keys.add(nk)
            vid = len(self.models)
            self.models.append(v.netlist)
            self.variants.append(v)
            for f in faults_for(v):
                for a in params:
                    cand = Cand(f, a, vid)
                    c = self._replayed(cand)
                    if c is not None:
                        self.cands[cand] = c
                        added += 1
                        self.wiring_region.update(v.region)
        return added

    def _expand_for_diagnosis(self) -> bool:
        """The leading answer is one component and mode: add the alternative wirings of the flagged regions
        around its parts, so a part is reported only if every wiring that fits the readings agrees."""
        left = self.faults_left
        kinds = {(f.component, f.mode) for f in left}
        if not self.variant_source or len(kinds) != 1:
            return False
        comp, mode = kinds.pop()
        terminals = {f"{comp}:{t}" for f in left if f.part for t in f.part.split("-")}
        if not terminals:
            return False
        params = sorted({c.params for c in self.cands}) or [()]
        before = len(self.cands)
        added = self._expand(terminals, lambda v: list(dict.fromkeys(
            [*left, *(f for f in all_faults(v.netlist) if f.component == comp and f.mode == mode)])), params)
        if added:
            self.notes.append(f"joint hypotheses: {added} (fault, wiring) candidates added for {comp} "
                              f"({before} before, {len(self.models) - 1} wiring variants so far)")
        return added > 0

    # ---------------------------------------------------------------- public

    def run(self) -> dict:
        start = self.tb.initial_observation()
        self.evidence.append({"step": 0, "type": "functional_test", "observation": "panel at the start"})
        self._record(0, "read_indicators", {}, start)
        for _ in range(MAX_STEPS):
            if self.gave_up:
                break
            expanded = self._expand_for_diagnosis()
            settled = len(self.cands) <= 1 or (self.joint and len(self.faults_left) <= 1)
            if not expanded and (settled or not self._step()):
                break
        return self._submit()

    # ---------------------------------------------------------------- engine

    def _predict(self, name: str, args: dict) -> tuple[dict, dict | None]:
        pred, states = {}, ({} if name in STATEFUL else None)
        for f, c in self.cands.items():
            k = c.clone() if states is not None else c
            try:
                pred[f] = simulate(k, name, args, self.amps)
            except CircuitError:
                pred[f] = UNSTABLE
            if states is not None:
                states[f] = k
        return pred, states

    def _apply(self, entry: dict, prediction: tuple[dict, dict | None]) -> bool:
        pred, states = prediction
        self.last_pred = pred
        entry["actual"] = observed(entry["tool"], entry["result"], self.amps)
        survivors = [f for f in self.cands if pred[f] == entry["actual"]]
        self.cands = {f: (states[f] if states else self.cands[f]) for f in survivors}
        return bool(self.cands)

    def _record(self, step: int, name: str, args: dict, result: dict, prediction=None) -> None:
        entry = {"step": step, "tool": name, "args": args, "result": result, "before": len(self.cands)}
        self.history.append(entry)
        before = dict(self.cands)
        ok = self._apply(entry, prediction or self._predict(name, args))
        entry["after"] = len(self.cands)
        if not ok:
            self._conflict(entry, before)
        if self.on_update:
            self.on_update(self, entry)

    def _conflict(self, entry: dict, before: dict) -> None:
        """No candidate explains the readings: the model netlist (or the single-fault catalog) is wrong."""
        self.conflicts += 1
        while not self.cands:
            if self.variant_source:
                old = before
                params = sorted({c.params for c in old}) or self.assignments
                alive = list(dict.fromkeys(c.fault for c in old))
                if self._expand(None, lambda v: list(dict.fromkeys(
                        [*alive, *(f for f in all_faults(v.netlist) if f.component in v.components)])), params):
                    self.variant_resolved += 1
                    self.notes.append(f"step {entry['step']}: explained by an alternative wiring of a flagged region "
                                      f"({len(self.cands)} candidates); no correction requested")
                    if self.on_event:
                        self.on_event({"type": "wiring_variants", "step": entry["step"], "candidates": len(self.cands),
                                       "faults": [str(f) for f in self.faults_left[:6]]})
                    return
            rejected = sum(bool(r.get("rejected")) for r in self.corrections)
            if rejected >= MAX_REJECTED:
                self.gave_up = True
                self.notes.append(f"step {entry['step']}: {rejected} correction proposals rejected; no more proposals, "
                                  "handing over to a human")
                return
            if not self.on_conflict or len(self.corrections) >= self.max_corrections:
                self.gave_up = True
                self.notes.append(f"step {entry['step']}: no candidate explains the readings; handing over to a human")
                return
            groups: dict = {}
            for f, outcome in self.last_pred.items():
                groups.setdefault(repr(outcome), (outcome, []))[1].append(str(f))
            ctx = {"entry": entry, "history": self.history, "netlist": self.n, "unknown_params": self.unknown,
                   "candidates": list(dict.fromkeys(str(c.fault) for c in before)),
                   "predicted": [{"outcome": o, "candidates": v} for o, v in groups.values()],
                   "healthy": self.healthy_outcomes(), "assignments": self.assignments,
                   "power0": self.power0, "amps": self.amps,
                   "rejected": [r for r in self.corrections if r.get("rejected") and r["step"] == entry["step"]]}
            new_netlist, record = self.on_conflict(ctx)
            record = {"step": entry["step"], **record}
            self.corrections.append(record)
            if new_netlist is None and record.get("rejected"):
                self.notes.append(f"step {entry['step']}: netlist correction rejected ({record['rejected']})")
                continue
            if new_netlist is None:
                self.gave_up = True
                self.notes.append(f"step {entry['step']}: no usable netlist correction; handing over to a human")
                return
            failed = self.set_model(new_netlist)
            record["candidates_after_replay"] = len(self.cands)
            if failed is not None:
                entry, before = failed, {}

    def _options(self) -> list[tuple]:
        """(name, args for the tool, predictions per candidate, new circuit per candidate or None, cost rank)."""
        opts = []
        power_on = self.tb.circuit.power
        if power_on:
            for p in self.points:
                pred = {f: _q(c.voltage(p, self.neutral)) for f, c in self.cands.items()}
                opts.append(("measure_voltage", {"point_a": p, "point_b": self.neutral}, pred, None, 0))
            # with wiring variants: readings across a part's own terminals, which do not depend on how the
            # rest of the circuit is wired (the probe pair is the part itself)
            across = [(p.a, p.b) for p in self.parts] if self.joint else []
            for a, b2 in across:
                pred = {f: _q(c.voltage(a, b2)) for f, c in self.cands.items()}
                opts.append(("measure_voltage", {"point_a": a, "point_b": b2}, pred, None, 0))
            probes = [(p, self.neutral) for p in self.points] + across
            for b in self.buttons:
                if b in self.starts and self.consecutive_starts >= self.tb.policy.max_consecutive_starts:
                    continue
                held, after, volts, states = {}, {}, {}, {}
                for f, c in self.cands.items():
                    k = c.clone()
                    states[f] = k
                    try:
                        k.hold(b)
                        k.step(HOLD_S)
                        held[f] = _view(k, self.amps)
                        volts[f] = {pp: _q(k.voltage(*pp)) for pp in probes}
                        k.release(b)
                        after[f] = _view(k, self.amps)
                    except (CircuitError, KeyError):
                        held[f] = after[f] = UNSTABLE
                        volts[f] = dict.fromkeys(probes, UNSTABLE)
                pred = {f: (held[f], (), after[f]) for f in self.cands}
                opts.append(("press_button", {"button": b, "hold_seconds": HOLD_S}, pred, states, 2))
                for pp in probes:
                    pred = {f: (held[f], (volts[f][pp],), after[f]) for f in self.cands}
                    args = {"button": b, "hold_seconds": HOLD_S,
                            "measure_while_held": [{"point_a": pp[0], "point_b": pp[1]}]}
                    opts.append(("press_button", args, pred, states, 1))
            pred, states = self._predict("wait", {"seconds": WAIT_S})
            opts.append(("wait", {"seconds": WAIT_S}, pred, states, 3))
            opts += self._restart_options(across)
        else:
            for p in self.parts:
                pred = {f: _ohms(c.resistance(p.a, p.b)) for f, c in self.cands.items()}
                opts.append(("measure_resistance", {"point_a": p.a, "point_b": p.b}, pred, None, 0))
        return opts

    @staticmethod
    def _expected_survivors(pred: dict) -> float:
        groups: dict = {}
        for outcome in pred.values():
            key = repr(outcome)
            groups[key] = groups.get(key, 0) + 1
        n = len(pred)
        return sum(g * g for g in groups.values()) / n

    def _restart_options(self, across: list[tuple]) -> list[tuple]:
        """Joint mode, two steps: press stop, then a start button while reading across a part. A contact that
        only closes during start-up (a star contactor) can be checked this way once the machine has moved on;
        neither step alone splits the candidates, so a one-step search would never take them."""
        if not across or not self.stop:
            return []
        opts = []
        stop = ("press_button", {"button": self.stop, "hold_seconds": HOLD_S})
        for s in self.starts:
            vals = {}
            for f, c in self.cands.items():
                k = c.clone()
                try:
                    first = simulate(k, *stop, self.amps)
                    k.hold(s)
                    k.step(HOLD_S)
                    held = _view(k, self.amps)
                    volts = {pp: _q(k.voltage(*pp)) for pp in across}
                    k.release(s)
                    vals[f] = (first, held, volts, _view(k, self.amps))
                except (CircuitError, KeyError):
                    vals[f] = None
            for pp in across:
                pred = {f: (UNSTABLE if v is None else (v[0], (v[1], (v[2][pp],), v[3]))) for f, v in vals.items()}
                second = ("press_button", {"button": s, "hold_seconds": HOLD_S,
                                           "measure_while_held": [{"point_a": pp[0], "point_b": pp[1]}]})
                opts.append(("sequence", [stop, second], pred, None, 4))
        return opts

    @staticmethod
    def _expected_faults(pred: dict) -> float:
        """Expected number of distinct faults left (joint mode: telling wirings apart that lead to the same
        fault is not worth a reading)."""
        groups: dict = {}
        for cand, outcome in pred.items():
            groups.setdefault(repr(outcome), []).append(cand.fault)
        n = len(pred)
        return sum(len(g) / n * len(set(g)) for g in groups.values())

    def _step(self) -> bool:
        n = len(self.faults_left) if self.joint else len(self.cands)
        opts = self._options()
        score = self._expected_faults if self.joint else self._expected_survivors
        scored = [(score(opt[2]), opt[4], i, opt) for i, opt in enumerate(opts)]
        useful = [s for s in scored if s[0] < n - 1e-9]
        if not useful:
            if self.tb.circuit.power:
                self.notes.append(f"no live action splits the {n} candidates: power off for resistance checks")
                self._execute(("set_power", {"on": False}, None, None, 0))
                return True
            self.notes.append(f"no action splits the remaining {n} candidates")
            return False
        _, _, _, best = min(useful, key=lambda s: (s[0], s[1], s[2]))
        self._execute(best)
        return True

    def _execute(self, opt: tuple) -> None:
        name, args, pred, states, _ = opt
        if name == "sequence":  # each step is executed and recorded on its own
            for sub_name, sub_args in args:
                if self.gave_up or not self.cands:
                    return
                self._execute((sub_name, sub_args, None, None, 0))
            return
        r = self.tb.call(name, args)
        if "error" in r:
            raise RuntimeError(f"info-gain planner action refused: {name} {args}: {r['error']}")
        step = r["step"]
        if name == "measure_voltage":
            self.evidence.append({"step": step, "type": "instrument_reading",
                                  "observation": f"{args['point_a']} to {args['point_b']}: {r['volts']} V"})
        elif name == "measure_resistance":
            self.evidence.append({"step": step, "type": "instrument_reading",
                                  "observation": f"{args['point_a']} to {args['point_b']}: {r['ohms']} ohm"})
        elif name == "press_button":
            if args.get("measure_while_held"):
                rd = r["readings"][0]
                self.evidence.append({"step": step, "type": "instrument_reading",
                                      "observation": f"{rd['point_a']} to {rd['point_b']} with {args['button']} held: "
                                                     f"{rd['volts']} V"})
            else:
                self.evidence.append({"step": step, "type": "functional_test", "observation": f"press {args['button']}"})
            if args["button"] in self.starts:
                self.consecutive_starts += 1
            elif args["button"] == self.stop:
                self.consecutive_starts = 0
        elif name == "wait":
            self.evidence.append({"step": step, "type": "functional_test", "observation": f"wait {args['seconds']} s"})
        self._record(step, name, args, r, (pred, states) if pred is not None else None)

    def _submit(self) -> dict:
        left = self.faults_left
        self.notes.append(f"{len(left)} candidate faults left: {', '.join(map(str, left[:6]))}")
        if self.gave_up or not left:
            args = {"outcome": "insufficient_information", "confidence": 0.0, "evidence": self.evidence[-4:]}
        else:
            kinds = {(f.component, f.mode) for f in left}
            parts = {f.part for f in left}
            if len(kinds) == 1:
                comp, mode = kinds.pop()
                args = {"outcome": "diagnosed", "component": comp, "part": parts.pop() if len(parts) == 1 else "",
                        "failure_mode": mode, "confidence": round(1 / len(left), 2) if len(parts) > 1 else 1.0,
                        "evidence": self.evidence[-6:]}
            else:
                args = {"outcome": "insufficient_information", "confidence": 0.0, "evidence": self.evidence[-6:]}
            if self.review and (args["outcome"] == "diagnosed" or self.joint):
                args = self.review(self, args)
        r = self.tb.call("submit_diagnosis", args)
        if "error" in r:
            raise RuntimeError(f"info-gain diagnosis rejected: {r['error']}")
        return self.tb.diagnosis
