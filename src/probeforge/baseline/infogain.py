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
the recorded readings, and continues.

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
# values a drawing usually does not print, by component type; with a param_grid the planner treats
# each missing one as unknown and keeps a candidate per grid value (log-spaced, not tuned to this circuit)
PARAM_KEYS = {"timer": "delay", "thermal_relay": "trip_time"}
DEFAULT_PARAM_GRID = {"delay": (1.0, 3.0, 10.0, 30.0), "trip_time": (3.0, 10.0, 30.0)}


class Cand(NamedTuple):
    """A candidate: one fault, plus a value for every parameter the model netlist does not know."""

    fault: Fault
    params: tuple = ()  # (("KT.delay", 3.0), ...)

    def __str__(self) -> str:
        return str(self.fault) + (" [" + ", ".join(f"{k}={v:g}" for k, v in self.params) + "]" if self.params else "")


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


class InfoGainBaseline:
    def __init__(self, circuit: Circuit, approver: Approver = deny_all, candidates: list[Fault] | None = None,
                 model: Netlist | None = None, on_conflict: Callable[[dict], tuple] | None = None,
                 on_event: Callable[[dict], None] | None = None, max_corrections: int = MAX_CORRECTIONS,
                 on_update: Callable[["InfoGainBaseline", dict], None] | None = None,
                 param_grid: dict[str, tuple] | None = None):
        self.tb = ToolBox(circuit, approver=approver, on_event=on_event)
        self.power0 = circuit.power
        self.on_conflict = on_conflict
        self.on_update = on_update  # called after every recorded reading (the UI shows the candidates)
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
        out = []
        try:
            c = Circuit(with_params(self.n, params))
            c.set_power(self.power0)
            for e in self.history:
                out.append(simulate(c, e["tool"], e["args"], self.amps))
        except CircuitError:
            pass
        return out + [UNSTABLE] * (len(self.history) - len(out))

    @property
    def faults_left(self) -> list[Fault]:
        return list(dict.fromkeys(c.fault for c in self.cands))

    # ---------------------------------------------------------------- public

    def run(self) -> dict:
        start = self.tb.initial_observation()
        self.evidence.append({"step": 0, "type": "functional_test", "observation": "panel at the start"})
        self._record(0, "read_indicators", {}, start)
        for _ in range(MAX_STEPS):
            if self.gave_up or len(self.cands) <= 1:
                break
            if not self._step():
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
                   "healthy": self.healthy_outcomes()}
            new_netlist, record = self.on_conflict(ctx)
            record = {"step": entry["step"], **record}
            self.corrections.append(record)
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
                        volts[f] = {p: _q(k.voltage(p, self.neutral)) for p in self.points}
                        k.release(b)
                        after[f] = _view(k, self.amps)
                    except CircuitError:
                        held[f] = after[f] = UNSTABLE
                        volts[f] = dict.fromkeys(self.points, UNSTABLE)
                pred = {f: (held[f], (), after[f]) for f in self.cands}
                opts.append(("press_button", {"button": b, "hold_seconds": HOLD_S}, pred, states, 2))
                for p in self.points:
                    pred = {f: (held[f], (volts[f][p],), after[f]) for f in self.cands}
                    args = {"button": b, "hold_seconds": HOLD_S,
                            "measure_while_held": [{"point_a": p, "point_b": self.neutral}]}
                    opts.append(("press_button", args, pred, states, 1))
            pred, states = self._predict("wait", {"seconds": WAIT_S})
            opts.append(("wait", {"seconds": WAIT_S}, pred, states, 3))
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

    def _step(self) -> bool:
        n = len(self.cands)
        opts = self._options()
        scored = [(self._expected_survivors(opt[2]), opt[4], i, opt) for i, opt in enumerate(opts)]
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
        r = self.tb.call("submit_diagnosis", args)
        if "error" in r:
            raise RuntimeError(f"info-gain diagnosis rejected: {r['error']}")
        return self.tb.diagnosis
