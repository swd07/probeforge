"""Troubleshooting sheet for the ATS dev families A and B, generated from the simulator (no API calls).

  python -m uv run python scripts/ats_troubleshooting.py

For each family: the symptom (the controller panel, event log and metering 60 s after the Normal source failed), every
possible cause (each catalog fault, and the documented compound fault, that gives exactly this symptom on our
redrawing), and a fixed list of checks in a safe order: live readings first (no isolation needed), then isolation of
both sources (approval tier), then resistances and the manual operation check. Checks are chosen greedily by
information gain over the joint result of the checks so far; each lists the expected reading for every cause and the
causes it separates. Predictions come from the same simulator and the same prediction code as the info-gain planner
(the frozen AtsInfoGain, used from outside). Writes docs/ATS_TROUBLESHOOTING.md and docs/ATS_TROUBLESHOOTING.json (the
UI view). Generated from the simulator, not reviewed by an engineer.
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_ats import case_faults, load_cases, scenario_bench  # noqa: E402

from probeforge.ats import AtsBench  # noqa: E402
from probeforge.ats.infogain import AtsInfoGain  # noqa: E402
from probeforge.ats.nextstep import reading_text  # noqa: E402

LABEL = "Generated from the simulator (our redrawing of drawing 978741), not reviewed by an engineer."
FAMILIES = {"A": "operator circuit failure: Emergency accepted, transfer commanded, the switch does not operate",
            "B": "generator running but not accepted: no transfer command"}
TOOL_TEXT = {"measure_voltage": "Voltage {a} to {b}", "measure_resistance": "Resistance {a} to {b}",
             "read_position_indicator": "Position indicator", "manual_operation_check": "Manual operation check, then resistance {a} to {b}"}


def cause_label(faults: tuple) -> str:
    return " + ".join(f"{f.component} {f.part or ''} {f.mode}".replace("  ", " ") for f in faults) or "no fault"


def check_label(tool: str, args: dict) -> str:
    pts = args.get("readings", [args])[0] if tool == "manual_operation_check" else args
    return TOOL_TEXT[tool].format(a=pts.get("point_a", ""), b=pts.get("point_b", ""))


def symptom(obs: dict) -> dict:
    return {"lights": [k for k, v in obs["lights"].items() if v], "display": obs["display"], "alarms": obs["alarms"],
            "generator": obs["generator"], "load_powered": obs["load_powered"],
            "metering": {"Normal": obs["metering"]["Normal"], "Emergency": obs["metering"]["Emergency"]},
            "events": [f"{e['event']}" + (f" ({e['cause']})" if e.get("cause") else "") for e in obs["events"]]}


def why_not_separated(group: list[str]) -> str:
    """Why no allowed reading separates a group of causes (from what the causes are)."""
    parts = {c.rsplit(" ", 1)[0] for c in group}
    if len(parts) == 1:
        return "the same part in both: the same repair"
    if all(c.split(" ")[0] in ("SE", "ER", "NR") for c in group):
        return "relay contacts inside the controller, between points that cannot be probed: the controller is the repair"
    return "no allowed reading tells them apart on the simulator"


def entropy(sizes: list[int]) -> float:
    total = sum(sizes)
    return -sum(s / total * math.log2(s / total) for s in sizes if s)


def phase(planner: AtsInfoGain, live: bool, keys: dict, checks: list, tier: str) -> None:
    """Greedy checks of one phase: each refines the partition of the causes by the joint expected readings."""
    planner._far = {}
    menu = planner._menu(live)
    pred = {}  # (check index) -> {cause: value}
    while True:
        best, best_h, best_vals = None, entropy([len(g) for g in groups(keys).values()]), None
        for i, (tool, args) in enumerate(menu):
            if i not in pred:
                pred[i] = {c.faults: planner._predict(c, tool, args) for c in planner.cands}
            vals = pred[i]
            h = entropy([len(g) for g in groups({k: v + (vals[k],) for k, v in keys.items()}).values()])
            if h > best_h + 1e-9:
                best, best_h, best_vals = i, h, vals
        if best is None:
            return
        tool, args = menu[best]
        before = groups(keys)
        for k in keys:
            keys[k] = keys[k] + (best_vals[k],)
        split = []  # per group of causes this check splits: expected reading -> causes (largest subgroup last)
        for g in before.values():
            sub: dict = {}
            for f in g:
                sub.setdefault(reading_text(tool, best_vals[f]), []).append(cause_label(f))
            if len(sub) > 1:
                split.append(sorted(([r, cs] for r, cs in sub.items()), key=lambda x: len(x[1])))
        checks.append({"check": check_label(tool, args), "tool": tool, "tier": tier,
                       "expected": {cause_label(f): reading_text(tool, best_vals[f]) for f in keys},
                       "separates": split})


def groups(keys: dict) -> dict:
    out: dict = {}
    for k, v in keys.items():
        out.setdefault(v, []).append(k)
    return out


def family_sheets(fam: str, cases: dict) -> list[dict]:
    """One sheet per distinct symptom among the family's dev cases (family B: one per open sensing phase)."""
    from probeforge.ats.infogain import observation
    from probeforge.ats.tools import AtsToolBox

    by_symptom: dict = {}
    for cid, c in cases.items():
        if c["family"] == fam:
            tb = AtsToolBox(scenario_bench(c))
            tb.initial_observation()
            by_symptom.setdefault(observation(tb), {})[cid] = c
    sheets = [sheet(fam, members) for members in by_symptom.values()]
    for i, s in enumerate(sheets):
        s["variant"] = f"{fam}{i + 1}" if len(sheets) > 1 else fam
    return sheets


def sheet(fam: str, members: dict) -> dict:
    first = next(iter(members.values()))
    planner = AtsInfoGain(scenario_bench(first), AtsBench().n, model_key="true")
    planner.tb.initial_observation()
    planner._build()  # every candidate with the same panel, event log and metering as this case
    causes = [c.faults for c in planner.cands if c.faults]
    keys = {c.faults: () for c in planner.cands if c.faults}
    planner.cands = [c for c in planner.cands if c.faults]
    checks: list = []
    phase(planner, True, keys, checks, "allowed (live, sources on)")
    if len(groups(keys)) < len(keys):
        iso = planner.tb.call("isolate_sources", {"reason": "resistance checks and a manual operation check"})
        assert planner.tb.log[-1]["executed"], iso
        for c in planner.cands:  # the candidates follow the real bench into isolation
            c.tb.call("isolate_sources", {"reason": "replay"})
        checks.append({"check": "Isolate both sources (52U open, generator locked out)", "tool": "isolate_sources",
                       "tier": "approval (strong approval if the load were powered)", "expected": {}, "separates": []})
        phase(planner, False, keys, checks, "allowed only with both sources isolated")
    left = [[cause_label(f) for f in g] for g in groups(keys).values() if len(g) > 1]
    left_why = [why_not_separated(g) for g in left]
    covered = [cid for cid, c in members.items() if tuple(case_faults(c)) in causes]
    return {"family": fam, "title": FAMILIES[fam], "dev_cases": list(members), "dev_cases_covered": covered,
            "symptom": symptom(planner.tb.log[0]["result"]), "causes": [cause_label(f) for f in causes],
            "checks": checks, "not_separated": left, "not_separated_why": left_why}


def markdown(sheets: list[dict]) -> str:
    out = ["# ATS troubleshooting sheet (families A and B)", "", f"**{LABEL}**", "",
           "Source: `scripts/ats_troubleshooting.py`. Each sheet starts 60 s after the Normal source failed, switch on "
           "Normal, generator healthy. Causes are every catalog fault (and the documented compound fault of the coil "
           "burnout chain) that gives exactly this symptom on the simulator. Checks are in a safe order (live readings, "
           "then isolation, then resistances and the manual operation check), each chosen to split the remaining causes "
           "best; the table gives the expected reading for every cause. The simulator's assumptions and limits are in "
           "docs/ATS_MODEL.md.", ""]
    for s in sheets:
        sy = s["symptom"]
        out += [f"## {s['variant']}. Family {s['family']}: {s['title']}", "", "### Symptom", "",
                f"- Lights on: {', '.join(sy['lights']) or 'none'}; display: {sy['display']}; alarms: {', '.join(sy['alarms']) or 'none'}",
                f"- Generator: {sy['generator']}; load powered: {'yes' if sy['load_powered'] else 'no (on UPS)'}",
                f"- Metering Normal {'/'.join(str(v) for v in sy['metering']['Normal'])} V, Emergency "
                f"{'/'.join(str(v) for v in sy['metering']['Emergency'])} V",
                f"- Event log: {'; '.join(sy['events'])}", "",
                f"### Possible causes ({len(s['causes'])})", ""]
        out += [f"{i}. {c}" for i, c in enumerate(s["causes"], 1)]
        out += ["", "### Checks in safe order", ""]
        for i, c in enumerate(s["checks"], 1):
            parts = []
            for g in c["separates"]:
                parts += [f"{r}: {', '.join(cs)}" for r, cs in g[:-1]]
                parts.append(f"{g[-1][0]}: the other {len(g[-1][1])}" if len(g[-1][1]) > 2 else f"{g[-1][0]}: {', '.join(g[-1][1])}")
            out.append(f"{i}. **{c['check']}** ({c['tier']})" + (f". {'; '.join(parts)}" if parts else ""))
        meas = [c for c in s["checks"] if c["expected"]]
        out += ["", "### Expected reading per cause", "",
                "| Cause | " + " | ".join(f"{i}. {c['check']}" for i, c in enumerate(s["checks"], 1) if c["expected"]) + " |",
                "|---|" + "---|" * len(meas)]
        for cause in s["causes"]:
            out.append(f"| {cause} | " + " | ".join(c["expected"][cause] for c in meas) + " |")
        out += [""]
        if s["not_separated"]:
            out += ["No reading in the menu searched (voltages, resistances, the position indicator, the manual operation check; a repeat transfer needs strong approval and is not used) separates: "
                    + "; ".join(f"{', '.join(g)} ({w})" for g, w in zip(s["not_separated"], s["not_separated_why"])) + ".", ""]
        out += [f"Dev cases with this symptom: {', '.join(s['dev_cases'])} (all among the causes: "
                f"{'yes' if s['dev_cases_covered'] == s['dev_cases'] else 'no'}).", ""]
    return "\n".join(out)


def main() -> None:
    cases = load_cases()
    sheets = [s for f in FAMILIES for s in family_sheets(f, cases)]
    for s in sheets:
        print(f"sheet {s['variant']}: {len(s['causes'])} causes, {len(s['checks'])} checks, not separated "
              f"{s['not_separated']}, dev cases covered {s['dev_cases_covered']} of {s['dev_cases']}")
    (ROOT / "docs" / "ATS_TROUBLESHOOTING.md").write_text(markdown(sheets), encoding="utf-8")
    (ROOT / "docs" / "ATS_TROUBLESHOOTING.json").write_text(json.dumps({"label": LABEL, "sheets": sheets}, indent=2),
                                                            encoding="utf-8")
    print("written docs/ATS_TROUBLESHOOTING.md and docs/ATS_TROUBLESHOOTING.json")


if __name__ == "__main__":
    main()
