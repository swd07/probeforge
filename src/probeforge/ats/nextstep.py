"""The information-gain planner's next step, for the UI: what it will do next and which causes each possible result
keeps. Not part of the frozen hybrid: it reads the frozen planner (AtsInfoGain) from its update hook, using the
planner's own choice (_best) and prediction (_predict), and changes nothing. The run loop calls the update hook right
before it chooses, with nothing in between, so the plan shown is the step the run takes next
(scripts/ats_nextstep_identity.py checks this and that runs with and without the hook are identical).

The planner works on its own model netlist (a transcription for the hybrid, our redrawing for the Engineer-mode
suggestion), never on the injected fault.
"""

import math

from probeforge.faults.model import Fault


def cause_text(f: Fault | None) -> str:
    return "no fault" if f is None else f"{f.component} {f.part or ''} {f.mode}".replace("  ", " ")


def reading_text(tool: str, value) -> str:
    if isinstance(value, tuple) and value[:1] == ("error",):
        return "probe point not in this model"
    if tool == "measure_voltage":
        return f"{value:g} V" if isinstance(value, float | int) else str(value)
    if tool == "measure_resistance":
        return "open" if value in ("open", math.inf) else f"{value:g} ohm"
    if tool == "manual_operation_check" and isinstance(value, tuple):
        moved, ohms = value
        return ("moves" if moved else "does not move") + ", reads " + ", ".join("open" if v == "open" else f"{v:g} ohm" for v in ohms)
    return str(value)


def _points(tool: str, args: dict) -> list[str]:
    if tool in ("measure_voltage", "measure_resistance"):
        return [args["point_a"], args["point_b"]]
    if tool == "manual_operation_check":
        return [p for r in args.get("readings", []) for p in (r["point_a"], r["point_b"])]
    return []


def planned_next(planner, max_causes: int = 6) -> dict:
    """The planner's next step as the run loop will take it (AtsInfoGain.run): submit when one root cause is left or
    the action budget is spent; otherwise the best reading for the current phase (live readings until the switch is
    isolated); when live readings no longer split the causes, the isolation request."""
    roots = []
    for c in planner.cands:
        if c.root not in roots:
            roots.append(c.root)
    base = {"causes_left": len(roots), "candidates": len(planner.cands)}
    if len(planner.steps) >= planner.max_actions or len(roots) <= 1:
        return {**base, "tool": "submit_diagnosis", "args": {}, "points": [], "outcomes": [],
                "why": "one root cause left" if len(roots) == 1 else
                       "no candidate explains every reading" if not roots else "action budget spent"}
    live = not planner.tb.bench.isolated
    choice, gain = planner._best(live)
    if choice is None:
        if live:
            return {**base, "tool": "isolate_sources", "args": {}, "points": [], "outcomes": [],
                    "why": "live readings no longer separate the remaining causes: isolation (approval) for resistance "
                           "checks and a manual operation check"}
        return {**base, "tool": "submit_diagnosis", "args": {}, "points": [], "outcomes": [],
                "why": "no reading separates the remaining causes"}
    tool, args = choice
    groups: dict = {}
    for c in planner.cands:
        roots_here = groups.setdefault(planner._predict(c, tool, args), [])
        if c.root not in roots_here:
            roots_here.append(c.root)
    outcomes = [{"reading": reading_text(tool, v), "n": len(rs), "causes": [cause_text(r) for r in rs[:max_causes]]}
                for v, rs in sorted(groups.items(), key=lambda kv: (len(kv[1]), str(kv[0])))]
    return {**base, "tool": tool, "args": {k: v for k, v in args.items() if k != "reason"}, "points": _points(tool, args),
            "gain_bits": round(gain, 3), "outcomes": outcomes, "why": "splits the remaining causes best (information gain)"}
