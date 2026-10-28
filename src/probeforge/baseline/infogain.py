"""Information-gain baseline: a perfect-model diagnostician.

It keeps every single fault the catalog defines as a candidate, simulates each candidate in lock
step with the real panel, and at every step takes the action whose predicted outcomes split the
surviving candidates best (smallest expected number of survivors). Readings that a candidate does
not reproduce exactly eliminate it.

This is not a fair peer of the agent: it needs a complete and exact fault model of this very
circuit (every possible fault, simulated with the same simulator that produces the readings),
which the agent does not have. It shows how far measurement choice alone can go with perfect
knowledge.

It uses the same ToolBox and policy as the agent: voltage only live, resistance only dead, at most
3 consecutive start presses, and it never re-applies power (that would need approval after a trip).
"""

from probeforge.faults.catalog import all_faults
from probeforge.faults.model import Fault
from probeforge.sim import Circuit
from probeforge.tools.toolbox import Approver, ToolBox, deny_all

HOLD_S = 0.2
WAIT_S = 7.0
MAX_STEPS = 60


def _view(c: Circuit) -> tuple:
    ind = c.indicators()
    return (
        tuple(sorted(ind["lamps"].items())),
        ind["motor"],
        tuple(sorted(ind["phase_currents"].items())),
        tuple(sorted(ind["line_currents_a"].items())),
        c.power,
    )


def _result_view(r: dict) -> tuple:
    return (
        tuple(sorted(r["lamps"].items())),
        r["motor"],
        tuple(sorted(r["line_currents"].items())),
        tuple(sorted(r["line_currents_a"].items())),
        r["power_switch"] == "on",
    )


def _ohms(c: Circuit, a: str, b: str):
    v = c.resistance(a, b)
    return "open" if v == float("inf") else v


class InfoGainBaseline:
    def __init__(self, circuit: Circuit, approver: Approver = deny_all, candidates: list[Fault] | None = None):
        self.n = circuit.netlist
        self.tb = ToolBox(circuit, approver=approver)
        self.neutral = self.n.neutral
        buttons = self.n.components_of("button")
        self.stop = next(b.id for b in buttons if b.label.lower().startswith("stop"))
        self.starts = [b.id for b in buttons if b.label.lower().startswith("start")]
        self.buttons = [b.id for b in buttons]
        self.nets = [net for net in self.n.nets if net != self.neutral]
        self.parts = list(self.n.parts.values())
        self.cands: dict[Fault, Circuit] = {}
        for f in candidates or all_faults(self.n):
            c = Circuit(self.n)
            c.apply_fault(f)
            c.set_power(circuit.power)
            self.cands[f] = c
        self.consecutive_starts = 0
        self.evidence: list[dict] = []
        self.notes: list[str] = []

    # ---------------------------------------------------------------- public

    def run(self) -> dict:
        start = self.tb.initial_observation()
        self._filter(lambda c: _view(c), _result_view({**start, "power_switch": start["power_switch"]}))
        self.evidence.append({"step": 0, "type": "functional_test", "observation": "panel at the start"})
        for _ in range(MAX_STEPS):
            if len(self.cands) <= 1:
                break
            if not self._step():
                break
        return self._submit()

    # ---------------------------------------------------------------- engine

    def _filter(self, predict, actual) -> None:
        self.cands = {f: c for f, c in self.cands.items() if predict(c) == actual}

    def _options(self) -> list[tuple]:
        """(name, args for the tool, predictions per candidate, new circuit per candidate or None, cost rank)."""
        opts = []
        power_on = self.tb.circuit.power
        if power_on:
            for net in self.nets:
                pred = {f: c.voltage(net, self.neutral) for f, c in self.cands.items()}
                opts.append(("measure_voltage", {"point_a": net, "point_b": self.neutral}, pred, None, 0))
            for b in self.buttons:
                if b in self.starts and self.consecutive_starts >= self.tb.policy.max_consecutive_starts:
                    continue
                held, after, volts, states = {}, {}, {}, {}
                for f, c in self.cands.items():
                    k = c.clone()
                    k.hold(b)
                    k.step(HOLD_S)
                    held[f] = _view(k)
                    volts[f] = {net: k.voltage(net, self.neutral) for net in self.nets}
                    k.release(b)
                    after[f] = _view(k)
                    states[f] = k
                pred = {f: (held[f], after[f]) for f in self.cands}
                opts.append(("press_button", {"button": b, "hold_seconds": HOLD_S}, pred, states, 2))
                for net in self.nets:
                    pred = {f: (held[f], volts[f][net], after[f]) for f in self.cands}
                    args = {"button": b, "hold_seconds": HOLD_S,
                            "measure_while_held": [{"point_a": net, "point_b": self.neutral}]}
                    opts.append(("press_button", args, pred, states, 1))
            states, pred = {}, {}
            for f, c in self.cands.items():
                k = c.clone()
                k.step(WAIT_S)
                states[f], pred[f] = k, _view(k)
            opts.append(("wait", {"seconds": WAIT_S}, pred, states, 3))
        else:
            for p in self.parts:
                pred = {f: _ohms(c, p.a, p.b) for f, c in self.cands.items()}
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
            raise RuntimeError(f"info-gain baseline action refused: {name} {args}: {r['error']}")
        step = r["step"]
        if name == "set_power":
            for c in self.cands.values():
                c.set_power(args["on"])
            return
        if name == "measure_voltage":
            actual = r["volts"]
            self.evidence.append({"step": step, "type": "instrument_reading",
                                  "observation": f"{args['point_a']} to N: {actual} V"})
        elif name == "measure_resistance":
            actual = r["ohms"]
            self.evidence.append({"step": step, "type": "instrument_reading",
                                  "observation": f"{args['point_a']} to {args['point_b']}: {actual} ohm"})
        elif name == "press_button":
            held, after = _result_view(r["while_held"]), _result_view(r["after_release"])
            if args.get("measure_while_held"):
                actual = (held, r["readings"][0]["volts"], after)
                self.evidence.append({"step": step, "type": "instrument_reading",
                                      "observation": f"{r['readings'][0]['point_a']} to N with {args['button']} held: "
                                                     f"{r['readings'][0]['volts']} V"})
            else:
                actual = (held, after)
                self.evidence.append({"step": step, "type": "functional_test", "observation": f"press {args['button']}"})
            if args["button"] in self.starts:
                self.consecutive_starts += 1
            elif args["button"] == self.stop:
                self.consecutive_starts = 0
        else:  # wait
            actual = _result_view(r)
            self.evidence.append({"step": step, "type": "functional_test", "observation": f"wait {args['seconds']} s"})
        survivors = {f for f in self.cands if pred[f] == actual}
        if states:
            self.cands = {f: states[f] for f in survivors}
        else:
            self.cands = {f: c for f, c in self.cands.items() if f in survivors}

    def _submit(self) -> dict:
        left = list(self.cands)
        self.notes.append(f"{len(left)} candidates left: {', '.join(map(str, left[:6]))}")
        if not left:
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
