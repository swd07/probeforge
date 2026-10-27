"""Run the agent or the baseline on a fault suite and print a results table.

Usage:
  uv run python scripts/run_scenarios.py                          # agent, s01-s08
  uv run python scripts/run_scenarios.py --suite holdout --effort low --workers 8
  uv run python scripts/run_scenarios.py --runner baseline --suite all
  uv run python scripts/run_scenarios.py --repeat 3 --effort low

Suites: scenarios (s01-s08), holdout (30 random visible + 10 latent faults, seed 2026,
none of the 8 scenario faults), all (both). For latent faults, insufficient_information
counts as correct.

Writes runs/<timestamp>_<runner>_<suite>_<effort>/: one trace per case (no fault inside),
results.json and results.md (with the expected fault and the score).
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from probeforge.agent.client import MUSE_SPARK, make_client
from probeforge.agent.loop import run_agent
from probeforge.baseline import HalfSplitBaseline
from probeforge.eval.scoring import score
from probeforge.faults import Fault
from probeforge.faults.catalog import load_scenarios, make_holdout
from probeforge.sim import Circuit, Netlist

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT_SEED = 2026


@dataclass
class Case:
    id: str
    circuit: Path
    fault: Fault
    latent: bool


def build_cases(suite: str) -> list[Case]:
    scenarios = load_scenarios()
    cases = []
    if suite in ("scenarios", "all"):
        cases += [Case(s.id, s.circuit, s.fault, False) for s in scenarios]
    if suite in ("holdout", "all"):
        circuit = scenarios[0].circuit
        visible, latent = make_holdout(Netlist.load(circuit), HOLDOUT_SEED, exclude=[s.fault for s in scenarios])
        cases += [Case(f"h{i:02d}", circuit, f, False) for i, f in enumerate(visible, 1)]
        cases += [Case(f"l{i:02d}", circuit, f, True) for i, f in enumerate(latent, 1)]
    return cases


def evidence_counts(diagnosis: dict | None) -> tuple[int, int]:
    ev = (diagnosis or {}).get("evidence") or []
    return (sum(e.get("type") == "functional_test" for e in ev), sum(e.get("type") == "instrument_reading" for e in ev))


def run_case(case: Case, args, client, out_dir: Path, rep: int) -> dict:
    circuit = Circuit.load(case.circuit)
    circuit.apply_fault(case.fault)
    circuit.set_power(True)
    t0 = time.perf_counter()
    if args.runner == "agent":
        run, tb = run_agent(circuit, client, model=args.model, effort=args.effort, max_turns=args.max_turns)
        diagnosis, outcome, error = run.diagnosis, run.outcome, run.error
        tokens = {"prompt": run.prompt_tokens, "cached": run.cached_tokens, "completion": run.completion_tokens}
        cost, turns, protocol_errors, turn_log = run.cost_usd, run.turns, run.protocol_errors, run.turn_log
        notes, recovered = [], run.recovered_text_calls
    else:
        baseline = HalfSplitBaseline(circuit)
        diagnosis = baseline.run()
        tb = baseline.tb
        outcome, error = diagnosis.get("outcome"), None
        tokens, cost, turns, protocol_errors, turn_log = {"prompt": 0, "cached": 0, "completion": 0}, 0.0, 0, 0, []
        notes, recovered = baseline.notes, 0
    seconds = round(time.perf_counter() - t0, 1)

    name = case.id if args.repeat == 1 else f"{case.id}_r{rep}"
    trace = {
        "case": name, "runner": args.runner, "model": args.model if args.runner == "agent" else None,
        "effort": args.effort, "outcome": outcome, "diagnosis": diagnosis, "turns": turns,
        "protocol_errors": protocol_errors, "recovered_text_calls": recovered, "measurements": tb.measurements,
        "redundant_measurements": tb.redundant_measurements, "tool_calls": tb.step,
        "policy": {"blocked": tb.policy.stats.blocked, "approval_requests": tb.policy.stats.approval_requests,
                   "approvals_denied": tb.policy.stats.approvals_denied,
                   "blocked_actions": tb.policy.stats.blocked_actions},
        "tokens": tokens, "cost_usd": cost, "seconds": seconds, "error": error, "notes": notes,
        "turn_log": turn_log, "tool_log": tb.log, "hypotheses_history": tb.hypotheses_history,
    }
    (out_dir / f"{name}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")

    s = score(diagnosis, case.fault)
    exact = s["component_ok"] and s["mode_ok"]
    correct = exact or (case.latent and outcome == "insufficient_information")
    d = diagnosis or {}
    func, inst = evidence_counts(diagnosis)
    return {
        "case": name, "latent": case.latent, "expected": str(case.fault),
        "diagnosed": f"{d.get('component', '')}:{d.get('part') or ''} {d.get('failure_mode', '')}".replace(": ", " ")
        if outcome == "diagnosed" else outcome,
        "confidence": d.get("confidence"), **s, "correct": correct, "outcome": outcome,
        "measurements": tb.measurements, "redundant": tb.redundant_measurements, "tool_calls": tb.step,
        "turns": turns, "policy_blocked": tb.policy.stats.blocked, "approvals_denied": tb.policy.stats.approvals_denied,
        "protocol_errors": protocol_errors, "recovered_text_calls": recovered,
        "evidence_functional": func, "evidence_instrument": inst,
        "tokens": tokens["prompt"] + tokens["completion"], "cost_usd": cost, "seconds": seconds, "error": error,
    }


def yes(b: bool) -> str:
    return "yes" if b else "no"


def render(rows: list[dict], title: str, wall: float) -> str:
    header = ("| Case | Expected | Diagnosis | Correct | Component | Mode | Part | Meas | Redundant | Evidence F/I "
              "| Blocks | Turns | Tokens | Cost $ | Seconds |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    lines = [
        f"| {r['case']}{' (latent)' if r['latent'] else ''} | {r['expected']} | {r['diagnosed']} | {yes(r['correct'])} "
        f"| {yes(r['component_ok'])} | {yes(r['mode_ok'])} | {yes(r['part_ok'])} | {r['measurements']} | {r['redundant']} "
        f"| {r['evidence_functional']}/{r['evidence_instrument']} | {r['policy_blocked']} | {r['turns']} "
        f"| {r['tokens']} | {r['cost_usd']:.3f} | {r['seconds']} |"
        for r in rows
    ]
    n = len(rows)
    vis = [r for r in rows if not r["latent"]]
    lat = [r for r in rows if r["latent"]]
    summary = [
        f"**{title}**",
        "",
        f"- Correct: {sum(r['correct'] for r in rows)}/{n}"
        + (f" (visible {sum(r['correct'] for r in vis)}/{len(vis)}, latent {sum(r['correct'] for r in lat)}/{len(lat)})" if lat else ""),
        f"- Component right: {sum(r['component_ok'] for r in vis)}/{len(vis)} visible; failure mode right: {sum(r['mode_ok'] for r in vis)}/{len(vis)}; "
        f"exact incl. part: {sum(r['mode_ok'] and r['part_ok'] for r in vis)}/{len(vis)}",
        f"- Measurements: {sum(r['measurements'] for r in rows)} total, {sum(r['measurements'] for r in rows) / max(n, 1):.1f} per case; "
        f"redundant {sum(r['redundant'] for r in rows)}",
        f"- Evidence items: {sum(r['evidence_functional'] for r in rows)} functional_test, {sum(r['evidence_instrument'] for r in rows)} instrument_reading",
        f"- Policy blocks: {sum(r['policy_blocked'] for r in rows)}, protocol errors: {sum(r['protocol_errors'] for r in rows)}, "
        f"tool calls recovered from text: {sum(r['recovered_text_calls'] for r in rows)}, "
        f"errors: {sum(1 for r in rows if r['error'])}",
        f"- Tokens: {sum(r['tokens'] for r in rows)}, cost ${sum(r['cost_usd'] for r in rows):.3f} "
        f"(${sum(r['cost_usd'] for r in rows) / max(n, 1):.3f} per case)",
        f"- Time: {sum(r['seconds'] for r in rows):.0f} s summed over cases, {wall:.0f} s wall clock",
    ]
    return "\n".join(summary) + "\n\n" + "\n".join([header, *lines]) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", choices=["agent", "baseline"], default="agent")
    ap.add_argument("--suite", choices=["scenarios", "holdout", "all"], default="scenarios")
    ap.add_argument("--model", default=MUSE_SPARK)
    ap.add_argument("--effort", default=None, help="reasoning_effort: minimal, low, medium, high, xhigh")
    ap.add_argument("--only", nargs="*", default=None, help="case ids, e.g. s01 h05")
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    cases = [c for c in build_cases(args.suite) if not args.only or c.id in args.only]
    jobs = [(c, rep) for rep in range(1, args.repeat + 1) for c in cases]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"{stamp}_{args.runner}_{args.suite}" + (f"_{args.effort or 'default'}" if args.runner == "agent" else "")
    out_dir = ROOT / "runs" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    client = make_client() if args.runner == "agent" else None

    started = time.perf_counter()

    def job(item):
        case, rep = item
        row = run_case(case, args, client, out_dir, rep)
        print(f"{row['case']}: {row['diagnosed']} (expected {row['expected']}) correct={yes(row['correct'])} "
              f"meas={row['measurements']} {row['seconds']}s" + (f" ERROR {row['error']}" if row["error"] else ""), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows = list(pool.map(job, jobs))
    wall = time.perf_counter() - started

    who = f"{args.model}, effort {args.effort or 'default'}" if args.runner == "agent" else "half-split baseline"
    table = render(rows, f"{args.runner} on {args.suite} ({who}), {len(rows)} runs", wall)
    print("\n" + table)
    (out_dir / "results.md").write_text(table, encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps({"args": vars(args), "wall_s": wall, "rows": rows}, indent=2), encoding="utf-8")
    print(f"Traces: {out_dir}")


if __name__ == "__main__":
    main()
