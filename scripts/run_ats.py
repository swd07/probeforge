"""Run the ATS agent profile on ATS dev cases and write a results table.

  python -m uv run python scripts/run_ats.py --cases a1_coil_open a4_cutoff_8_9 --effort low

Every case starts the same way: the Normal source fails at time 0 and the agent is called 60 s later. The approver is
the batch approver (approves the approval tier, denies every strong approval). Writes runs/<timestamp>_ats_agent_<effort>/:
one trace per case (no fault inside) plus results.md and results.json (with the expected fault, for scoring only).
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from probeforge.agent.client import MUSE_SPARK, make_client  # noqa: E402
from probeforge.ats import AtsBench  # noqa: E402
from probeforge.agent.loop import _cost  # noqa: E402
from probeforge.ats.agent import run_ats_agent  # noqa: E402
from probeforge.ats.agent_responses import run_ats_agent_responses  # noqa: E402
from probeforge.ats.ambiguity import signature  # noqa: E402
from probeforge.ats.faults import all_faults  # noqa: E402
from probeforge.eval.scoring import grade  # noqa: E402
from probeforge.eval.spend import SpendLedger, SpendLimitError  # noqa: E402
from probeforge.faults.model import Fault  # noqa: E402

OUTAGE_S = 60.0
EST_PER_CASE_USD = 0.20


def load_cases() -> dict[str, dict]:
    return {d["id"]: d for d in (yaml.safe_load(p.read_text(encoding="utf-8"))
                                 for p in sorted((ROOT / "scenarios" / "ats").glob("*.yaml")))}


def _f(d: dict) -> Fault:
    return Fault(d["component"], d["mode"], d.get("part"))


def case_faults(case: dict) -> list[Fault]:
    return [_f(x) for x in (case.get("faults") or [case["fault"]])]


def accepted_answers(case: dict) -> list[Fault]:
    """The root cause (or the single fault), plus any equally valid root cause listed in the case."""
    return [_f(case.get("root_cause") or case["fault"])] + [_f(x) for x in case.get("also_accepted") or []]


_catalog_sigs: dict | None = None


def twins_of(faults: list[Fault], exclude: list[Fault]) -> list[Fault]:
    """Single catalog faults that no bench observation tells apart from this case."""
    global _catalog_sigs
    if _catalog_sigs is None:
        _catalog_sigs = {f: signature([f]) for f in all_faults(AtsBench().n)}
    sig = signature(faults)
    return [f for f, s in _catalog_sigs.items() if s == sig and f not in exclude]


def scenario_bench(case: dict) -> AtsBench:
    b = AtsBench(faults=case_faults(case))
    b.lose_utility()
    b.step(OUTAGE_S)
    return b


class CapReached(Exception):
    pass


def run_case(cid: str, case: dict, args, client, out_dir: Path, ledger: SpendLedger, spent: list) -> dict | None:
    if args.cap and sum(spent) >= args.cap:  # the run's spending cap: no new case starts once it is reached
        return None
    bench = scenario_bench(case)
    t_start, ups_start = bench.t, bench.ups_left
    agent = run_ats_agent_responses if args.transport == "responses" else run_ats_agent
    run, tb = agent(bench, client, model=args.model, effort=args.effort, max_turns=args.max_turns)
    ledger.record(run.cost_usd, f"{out_dir.name}/{cid}")
    spent.append(run.cost_usd)
    trace = {"case": cid, "runner": "ats_agent", "model": run.model, "effort": run.effort, "outcome": run.outcome,
             "diagnosis": run.diagnosis, "turns": run.turns, "error": run.error, "log": tb.log,
             "hypotheses": tb.hypotheses_history, "turn_log": run.turn_log,
             "tokens": {"prompt": run.prompt_tokens, "cached": run.cached_tokens, "completion": run.completion_tokens},
             "cost_usd": run.cost_usd, "seconds": run.seconds, "transport": args.transport}
    (out_dir / f"{cid}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")

    d = run.diagnosis if run.outcome == "diagnosed" else {"outcome": run.outcome}
    answers = accepted_answers(case)
    twins = twins_of(case_faults(case), answers)
    grades = [grade(d, a, False, twins) for a in answers]
    g = next((x for x in grades if x["correct"]), grades[0])
    consequence = run.outcome == "diagnosed" and not g["correct"] and any(
        grade(d, f, False)["correct"] for f in case_faults(case) if f not in answers)
    s = tb.policy.stats
    dd = run.diagnosis or {}
    return {
        "case": cid, "family": case["family"], "expected": " or ".join(str(a) for a in answers),
        "diagnosed": f"{dd.get('component', '')}:{dd.get('part') or ''} {dd.get('failure_mode', '')}".replace(": ", " ")
        if run.outcome == "diagnosed" else run.outcome,
        "confidence": dd.get("confidence"), "correct": g["correct"], "component_ok": g["component_ok"],
        "justified": g["justified"], "confident_wrong": g["confident_wrong"], "consequence_not_cause": consequence,
        "twins": [str(t) for t in twins], "measurements": tb.measurements, "redundant": tb.redundant_measurements,
        "tool_calls": tb.step, "turns": run.turns, "policy_blocked": s.blocked, "never_attempts": s.never_attempts,
        "approval_requests": s.approval_requests, "strong_approval_requests": s.strong_approval_requests,
        "approvals_denied": s.approvals_denied, "missing_hypothesis_updates": run.missing_hypothesis_updates,
        "protocol_errors": run.protocol_errors, "virtual_s": round(bench.t - t_start, 1),
        "ups_used_s": round(ups_start - bench.ups_left, 1), "ups_left_s": round(bench.ups_left, 1),
        "tokens": run.prompt_tokens + run.completion_tokens, "cost_usd": run.cost_usd, "seconds": run.seconds,
        "prompt_tokens": run.prompt_tokens, "cached_tokens": run.cached_tokens,
        "reasoning_tokens": sum(x.get("reasoning_tokens", 0) for x in run.turn_log),
        # the same tokens without the cached-input discount (the decision uses this cost)
        "uncached_cost_usd": round(_cost(run.model, run.prompt_tokens, 0, run.completion_tokens), 4),
        "recovered_text_calls": run.recovered_text_calls, "nudges": run.nudges,
        "error": run.error,
    }


def table(rows: list[dict]) -> str:
    head = ("| Case | Expected | Diagnosis | Conf. | Part correct | Confidently wrong | Meas. | Blocked | Approval / strong "
            "requests (denied) | UPS used s | Tokens | Cost |")
    out = [head, "|" + "---|" * 12]
    for r in rows:
        out.append(f"| {r['case']} | {r['expected']} | {r['diagnosed']} | {r['confidence']} | "
                   f"{'yes' if r['correct'] else 'no'}{' (consequence, not cause)' if r['consequence_not_cause'] else ''} | "
                   f"{'yes' if r['confident_wrong'] else 'no'} | {r['measurements']} | {r['policy_blocked']} | "
                   f"{r['approval_requests']} / {r['strong_approval_requests']} ({r['approvals_denied']}) | "
                   f"{r['ups_used_s']} | {r['tokens']} | ${r['cost_usd']:.3f} |")
    n = len(rows)
    out.append(f"\nCorrect at part level: {sum(r['correct'] for r in rows)}/{n}; confidently wrong: "
               f"{sum(r['confident_wrong'] for r in rows)}; total cost ${sum(r['cost_usd'] for r in rows):.3f}.")
    return "\n".join(out)


def summary(rows: list[dict]) -> str:
    n = max(len(rows), 1)
    prompt = sum(r["prompt_tokens"] for r in rows) or 1
    return (f"\n\nReadings {sum(r['measurements'] for r in rows)} (redundant {sum(r['redundant'] for r in rows)}), "
            f"protocol errors {sum(r['protocol_errors'] for r in rows)}, reasoning tokens {sum(r['reasoning_tokens'] for r in rows)}, "
            f"cache hit rate {sum(r['cached_tokens'] for r in rows) / prompt:.1%}, cost ${sum(r['cost_usd'] for r in rows):.3f} "
            f"(uncached ${sum(r['uncached_cost_usd'] for r in rows):.3f}), mean wall time {sum(r['seconds'] for r in rows) / n:.0f} s "
            f"per case, errors {sum(1 for r in rows if r['error'])}.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", required=True)
    ap.add_argument("--model", default=MUSE_SPARK)
    ap.add_argument("--effort", default="low", help="reasoning_effort for the agent loop (low or below)")
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--transport", choices=("chat", "responses"), default="chat")
    ap.add_argument("--cap", type=float, default=0.0, help="spending cap for this run in USD (0: none)")
    args = ap.parse_args()
    if args.effort not in ("minimal", "low"):
        sys.exit("budget rule: the agent loop runs at low effort or below")
    cases = load_cases()
    unknown = [c for c in args.cases if c not in cases]
    if unknown:
        sys.exit(f"unknown cases: {unknown}")
    ledger = SpendLedger()
    estimate = EST_PER_CASE_USD * len(args.cases)
    try:
        ledger.check(estimate, force=args.force, what=f"ATS run of {len(args.cases)} cases")
    except SpendLimitError as e:
        sys.exit(str(e))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "runs" / f"{stamp}_ats_agent_{args.transport}_{args.effort}"
    out_dir.mkdir(parents=True)
    client = make_client()
    t0 = time.perf_counter()
    spent: list[float] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(lambda c: run_case(c, cases[c], args, client, out_dir, ledger, spent), args.cases))
    skipped = [c for c, r in zip(args.cases, rows) if r is None]
    rows = [r for r in rows if r is not None]
    md = (f"# ATS agent, {args.model}, effort {args.effort}, transport {args.transport} (dev cases, not holdout)\n\n"
          + table(rows) + summary(rows)
          + (f"\n\nSpending cap ${args.cap:.2f} reached: not run {skipped}." if skipped else "")
          + f"\n\nWall time {time.perf_counter() - t0:.0f} s.\n")
    (out_dir / "results.md").write_text(md, encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(md)
    print(f"Spend: ${ledger.total:.2f} of ${ledger.limit_usd:.2f}; written to {out_dir}")


if __name__ == "__main__":
    main()
