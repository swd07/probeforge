"""Run the agent on the hand-written scenarios and print a results table.

Usage:  uv run python scripts/run_scenarios.py [--effort low] [--only s01 s05] [--max-turns 30]

Writes runs/<timestamp>_<effort>/<scenario>.json (agent trace, no fault inside),
results.json and results.md (with the expected fault and the score).
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from probeforge.agent.client import MUSE_SPARK, make_client
from probeforge.agent.loop import run_agent
from probeforge.eval.scoring import score
from probeforge.faults.catalog import load_scenarios
from probeforge.sim import Circuit

ROOT = Path(__file__).resolve().parents[1]


def yes(b: bool) -> str:
    return "yes" if b else "no"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MUSE_SPARK)
    ap.add_argument("--effort", default=None, help="reasoning_effort: minimal, low, medium, high, xhigh")
    ap.add_argument("--only", nargs="*", default=None, help="scenario ids, e.g. s01 s05")
    ap.add_argument("--max-turns", type=int, default=30)
    args = ap.parse_args()

    scenarios = [s for s in load_scenarios() if not args.only or s.id in args.only]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "runs" / f"{stamp}_{args.effort or 'default'}"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = make_client()

    rows = []
    for sc in scenarios:
        circuit = Circuit.load(sc.circuit)
        circuit.apply_fault(sc.fault)
        circuit.set_power(True)
        t0 = time.perf_counter()
        run, tb = run_agent(circuit, client, model=args.model, effort=args.effort, max_turns=args.max_turns)
        trace = {
            "scenario": sc.id,
            "model": run.model,
            "effort": run.effort,
            "outcome": run.outcome,
            "diagnosis": run.diagnosis,
            "turns": run.turns,
            "nudges": run.nudges,
            "protocol_errors": run.protocol_errors,
            "measurements": tb.measurements,
            "tool_calls": tb.step,
            "policy": {
                "blocked": tb.policy.stats.blocked,
                "approval_requests": tb.policy.stats.approval_requests,
                "approvals_denied": tb.policy.stats.approvals_denied,
                "blocked_actions": tb.policy.stats.blocked_actions,
            },
            "tokens": {"prompt": run.prompt_tokens, "cached": run.cached_tokens, "completion": run.completion_tokens},
            "cost_usd": run.cost_usd,
            "seconds": run.seconds,
            "error": run.error,
            "turn_log": run.turn_log,
            "tool_log": tb.log,
            "hypotheses_history": tb.hypotheses_history,
        }
        (out_dir / f"{sc.id}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")

        s = score(run.diagnosis, sc.fault)
        d = run.diagnosis or {}
        row = {
            "scenario": sc.id,
            "expected": str(sc.fault),
            "diagnosed": f"{d.get('component', '')}:{d.get('part', '') or ''} {d.get('failure_mode', '')}".strip()
            if run.outcome == "diagnosed"
            else run.outcome,
            "confidence": d.get("confidence"),
            **s,
            "measurements": tb.measurements,
            "tool_calls": tb.step,
            "turns": run.turns,
            "policy_blocked": tb.policy.stats.blocked,
            "approvals_denied": tb.policy.stats.approvals_denied,
            "protocol_errors": run.protocol_errors,
            "tokens": run.prompt_tokens + run.completion_tokens,
            "cost_usd": run.cost_usd,
            "seconds": round(time.perf_counter() - t0, 1),
            "error": run.error,
        }
        rows.append(row)
        print(
            f"{sc.id}: {row['diagnosed']} (expected {row['expected']}) component={yes(s['component_ok'])} "
            f"mode={yes(s['mode_ok'])} meas={tb.measurements} tokens={row['tokens']} {row['seconds']}s"
            + (f" ERROR {run.error}" if run.error else ""),
            flush=True,
        )

    header = (
        "| Scenario | Expected | Diagnosis | Component | Failure mode | Measurements | Policy blocks "
        "| Tokens | Cost $ | Seconds |\n|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [
        f"| {r['scenario']} | {r['expected']} | {r['diagnosed']} | {yes(r['component_ok'])} | {yes(r['mode_ok'])} "
        f"| {r['measurements']} | {r['policy_blocked']} | {r['tokens']} | {r['cost_usd']:.3f} | {r['seconds']} |"
        for r in rows
    ]
    n = len(rows)
    totals = (
        f"\nModel {args.model}, reasoning effort {args.effort or 'default'}: "
        f"component {sum(r['component_ok'] for r in rows)}/{n}, failure mode {sum(r['mode_ok'] for r in rows)}/{n}, "
        f"{sum(r['measurements'] for r in rows)} measurements, {sum(r['policy_blocked'] for r in rows)} policy blocks, "
        f"{sum(r['tokens'] for r in rows)} tokens, ${sum(r['cost_usd'] for r in rows):.3f}, "
        f"{sum(r['seconds'] for r in rows):.0f} s"
    )
    table = "\n".join([header, *lines]) + "\n" + totals + "\n"
    print("\n" + table)
    (out_dir / "results.md").write_text(table, encoding="utf-8")
    (out_dir / "results.json").write_text(
        json.dumps({"model": args.model, "effort": args.effort, "rows": rows}, indent=2), encoding="utf-8"
    )
    print(f"Traces: {out_dir}")


if __name__ == "__main__":
    main()
