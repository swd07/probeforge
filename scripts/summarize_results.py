"""Build the agent vs baseline comparison from saved runs.

Usage:  uv run python scripts/summarize_results.py OUT.md LABEL=runs/<dir> [LABEL=runs/<dir> ...]

Each run directory holds results.json and per-case traces from run_scenarios.py.
Adds the observational-ambiguity check (eval/ambiguity.py) and per-scenario variance
for repeated runs.
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from probeforge.eval.ambiguity import justified, observational_twins
from probeforge.eval.engineer import engineer_reference, load_engineer_traces
from probeforge.faults import Fault

ROOT = Path(__file__).resolve().parents[1]
CIRCUIT = ROOT / "scenarios" / "circuits" / "star_delta_reversing.yaml"


def parse_fault(text: str) -> Fault:
    target, mode = text.split()
    comp, _, part = target.partition(":")
    return Fault(comp, mode, part or None)


def load(run_dir: Path) -> list[dict]:
    data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    rows = []
    for r in data["rows"]:
        trace = json.loads((run_dir / f"{r['case']}.json").read_text(encoding="utf-8"))
        fault = parse_fault(r["expected"])
        twins = observational_twins(str(CIRCUIT), fault)
        r["twins"] = [str(t) for t in twins]
        r["justified"] = justified(trace["diagnosis"], fault, twins, r["correct"])
        r["confident_wrong"] = r["outcome"] == "diagnosed" and not r["correct"] and not r["justified"]
        rows.append(r)
    return rows


def block(label: str, rows: list[dict]) -> list[str]:
    vis = [r for r in rows if not r["latent"]]
    lat = [r for r in rows if r["latent"]]
    n = len(rows)

    def frac(sel, key):
        return f"{sum(r[key] for r in sel)}/{len(sel)}" if sel else "-"

    return [
        f"| {label} | {frac(vis, 'correct')} | {frac(vis, 'justified')} | {frac(lat, 'correct')} "
        f"| {sum(r['confident_wrong'] for r in rows)} | {sum(r['outcome'] != 'diagnosed' for r in vis)} "
        f"| {sum(r['measurements'] for r in rows) / n:.1f} | {sum(r['redundant'] for r in rows)} "
        f"| {sum(r['evidence_functional'] for r in rows)}/{sum(r['evidence_instrument'] for r in rows)} "
        f"| {sum(r['policy_blocked'] for r in rows)} "
        f"| {sum(r.get('approval_requests', 0) for r in rows)}/{sum(r['approvals_denied'] for r in rows)} "
        f"| {sum(r.get('missing_hypothesis_updates', 0) for r in rows)} | {sum(r.get('recovered_text_calls', 0) for r in rows)} "
        f"| {sum(r['cost_usd'] for r in rows) / n:.3f} | {sum(r['seconds'] for r in rows) / n:.1f} |"
    ]


def variance(rows: list[dict]) -> list[str]:
    by = defaultdict(list)
    for r in rows:
        by[r["case"].split("_r")[0]].append(r)
    out = ["| Scenario | Correct runs | Measurements per run | Mean | Cost $ mean | Seconds mean |", "|---|---|---|---|---|---|"]
    for sid in sorted(by):
        rs = by[sid]
        meas = [r["measurements"] for r in rs]
        out.append(
            f"| {sid} | {sum(r['correct'] for r in rs)}/{len(rs)} | {', '.join(map(str, meas))} "
            f"| {statistics.mean(meas):.1f} | {statistics.mean(r['cost_usd'] for r in rs):.3f} "
            f"| {statistics.mean(r['seconds'] for r in rs):.1f} |"
        )
    return out


def engineer_section(runs) -> list[str]:
    """Engineer reference column: cases whose fault has a manual-mode trace in scenarios/engineer_traces/."""
    traces = load_engineer_traces()
    if not traces:
        return []
    out = ["", "### Engineer reference (manual mode traces)", "",
           "| Run | Case | Expected | Engineer verdict | Engineer meas | Run correct | Run meas |",
           "|---|---|---|---|---|---|---|"]
    for label, d in runs:
        for r in json.loads((d / "results.json").read_text(encoding="utf-8"))["rows"]:
            ref = engineer_reference(parse_fault(r["expected"]), traces)
            if ref:
                out.append(f"| {label} | {r['case']} | {r['expected']} | {ref['verdict']} ({ref['engineer']}) "
                           f"| {ref['measurements']} | {'yes' if r['correct'] else 'no'} | {r['measurements']} |")
    return out if len(out) > 5 else []


def main() -> None:
    out = Path(sys.argv[1])
    runs = [(a.split("=", 1)[0], ROOT / a.split("=", 1)[1]) for a in sys.argv[2:]]
    lines = [
        "| Run | Visible correct | Visible correct or justified | Latent correct | Confidently wrong "
        "| Visible not diagnosed | Meas per case | Redundant | Evidence F/I | Policy blocks | Approvals asked/denied "
        "| Missing hyp. updates | Text tool calls | Cost $ per case | Seconds per case |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    details = []
    for label, d in runs:
        rows = load(d)
        lines += block(label, rows)
        if any("_r" in r["case"] for r in rows):
            details += ["", f"### Variance: {label}", "", *variance(rows)]
        wrong = [r for r in rows if not r["correct"]]
        if wrong:
            details += ["", f"### Not correct: {label}", "", "| Case | Expected | Answer | Observational twins | Justified |", "|---|---|---|---|---|"]
            details += [f"| {r['case']} | {r['expected']} | {r['diagnosed']} | {', '.join(r['twins']) or '-'} | "
                        f"{'yes' if r['justified'] else 'no'} |" for r in wrong]
    details += engineer_section(runs)
    text = "\n".join(lines + details) + "\n"
    out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
