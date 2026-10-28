"""Correction acceptance rule for the Verify step.

A netlist correction may change what a fault-free machine does only where the real readings
contradict the current model. Two checks, both against the pre-correction model:

1. Recorded steps: for every action taken so far, each observed field (a lamp, the motor state, the
   line currents, a meter value) that the old model's fault-free prediction reproduces must still be
   reproduced by the new model's fault-free prediction.
2. A generic fault-free run (power on, each start button with a short and a long wait, the other
   start buttons, stop): a field may change only if fields of its kind were contradicted by some
   real reading. Kinds: each lamp, the motor (state, line currents and amps together, since they
   come from one behaviour), power, meter readings, and whether the circuit settles.

Unknown parameters (timer delay, trip time): "reproduces" means for some value on the grid; the
fault-free runs are compared value by value.
The rule uses only the model netlists and the real readings, never the true netlist.
"""

from probeforge.baseline.infogain import HOLD_S, PARAM_KEYS, UNSTABLE, run_actions
from probeforge.hybrid.llm import action_text
from probeforge.sim import Netlist

LONG_WAIT_S = 40.0  # longer than any value on the unknown-parameter grid
MAX_REASONS = 6


def healthy_sequence(netlist: Netlist) -> list[tuple[str, dict]]:
    buttons = netlist.components_of("button")
    stop = next((b.id for b in buttons if b.label.lower().startswith("stop")), None)
    starts = [b.id for b in buttons if b.label.lower().startswith("start")]

    def press(b: str) -> tuple[str, dict]:
        return "press_button", {"button": b, "hold_seconds": HOLD_S}

    acts: list[tuple[str, dict]] = [("read_indicators", {})]
    for s in starts:
        acts += [press(s), ("wait", {"seconds": 1.0}), ("wait", {"seconds": LONG_WAIT_S})]
        acts += [press(o) for o in starts if o != s]
        if stop:
            acts += [press(stop), ("wait", {"seconds": 1.0})]
    return acts


def _view_fields(v: tuple, prefix: str) -> dict:
    lamps, motor, currents, amps, power = v
    d = {f"{prefix}lamp {k}": lit for k, lit in lamps}
    d.update({f"{prefix}motor": motor, f"{prefix}currents": currents, f"{prefix}amps": amps, f"{prefix}power": power})
    return d


def fields(tool: str, outcome) -> dict:
    """An outcome split into the fields a technician would compare one by one."""
    if outcome == UNSTABLE:
        return {"settles": False}
    if tool == "measure_voltage":
        return {"settles": True, "volts": outcome}
    if tool == "measure_resistance":
        return {"settles": True, "ohms": outcome}
    if tool == "press_button":
        held, volts, after = outcome
        return {"settles": True, **_view_fields(held, "while held: "),
                **{f"volts {i + 1} while held": v for i, v in enumerate(volts)}, **_view_fields(after, "after release: ")}
    return {"settles": True, **_view_fields(outcome, "")}


def kind(field: str) -> str:
    k = field.split(": ", 1)[-1]
    if k.startswith("volts"):
        return "volts"
    return "motor" if k in ("motor", "currents", "amps") else k


def _params_for(netlist: Netlist, params: tuple) -> tuple:
    """The grid values that are still unknown in this netlist (a correction may print a value)."""
    keep = []
    for key, value in params:
        cid, name = key.split(".")
        c = netlist.components.get(cid)
        if c is not None and PARAM_KEYS.get(c.type) == name and name not in c.params:
            keep.append((key, value))
    return tuple(keep)


def healthy_changes(ctx: dict, new: Netlist) -> list[str]:
    """Reasons to reject the correction (empty: accept). ctx is the planner's conflict context."""
    old, history = ctx["netlist"], ctx["history"]
    grid = ctx.get("assignments") or [()]
    power0, amps = ctx["power0"], ctx["amps"]
    actions = [(e["tool"], e["args"]) for e in history]
    old_h = {a: run_actions(old, a, None, actions, power0, amps) for a in grid}
    new_h = {a: run_actions(new, _params_for(new, a), None, actions, power0, amps) for a in grid}
    reasons: list[str] = []
    contradicted: set[str] = set()
    for i, e in enumerate(history):
        real = fields(e["tool"], e["actual"])
        olds = {a: fields(e["tool"], old_h[a][i]) for a in grid}
        news = {a: fields(e["tool"], new_h[a][i]) for a in grid}
        for k, v in real.items():
            if not any(olds[a].get(k) == v for a in grid):
                contradicted.add(kind(k))
            elif not any(news[a].get(k) == v for a in grid):
                reasons.append(f"step {e['step']} ({action_text(e['tool'], e['args'])}), {k}: the real reading "
                               f"{v} matched the current model, the correction predicts {news[grid[0]].get(k)}")
    seq = healthy_sequence(old)
    for a in grid:
        o = run_actions(old, a, None, seq, power0, amps)
        n = run_actions(new, _params_for(new, a), None, seq, power0, amps)
        for (tool, args), x, y in zip(seq, o, n):
            fo, fn = fields(tool, x), fields(tool, y)
            for k in sorted(set(fo) | set(fn)):
                if fo.get(k) != fn.get(k) and kind(k) not in contradicted:
                    reasons.append(f"fault-free run, {action_text(tool, args)}, {k}: {fo.get(k)} becomes {fn.get(k)}, "
                                   f"but no real reading contradicted the current model's {kind(k)}")
    return list(dict.fromkeys(reasons))[:MAX_REASONS]
