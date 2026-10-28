"""Run the agent or the baseline on a fault suite and print a results table.

Usage:
  uv run python scripts/run_scenarios.py                          # agent, s01-s08
  uv run python scripts/run_scenarios.py --suite holdout --effort low --workers 8
  uv run python scripts/run_scenarios.py --runner baseline --suite all
  uv run python scripts/run_scenarios.py --repeat 3 --effort low

Suites: scenarios (s01-s08), dev (scenarios/holdout_dev.yaml: 30 visible + 10 latent faults, used
while tuning, so dev results), clean (scenarios/holdout_clean.yaml: every fault never used before,
the reported numbers), all (scenarios + dev). For latent faults, insufficient_information counts
as correct.

--approve: a simulated human approves every reset / re-power request (default: all denied).

Writes runs/<timestamp>_<runner>_<suite>_<effort>/: one trace per case (no fault inside),
results.json and results.md (with the expected fault and the score).
"""

import argparse
import hashlib
import inspect
import json

import yaml
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from probeforge.agent.client import MUSE_SPARK, make_client
from probeforge.agent.loop import IMAGE_ONLY_PROMPT_EDITS, run_agent
from probeforge.baseline import HalfSplitBaseline, InfoGainBaseline
from probeforge.eval.scoring import score
from probeforge.eval.spend import EST_PER_AGENT_RUN_USD, SpendLedger, SpendLimitError
from probeforge.eval.trace import make_trace
from probeforge.faults import Fault
from probeforge.faults.catalog import SCENARIOS_DIR, load_scenarios
from probeforge.hybrid import run_hybrid
from probeforge.sim import Circuit, Netlist
from probeforge.sim.schematic import render_png
from probeforge.tools import approve_all, deny_all

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT_FILES = {"dev": "holdout_dev.yaml", "clean": "holdout_clean.yaml"}


@dataclass
class Case:
    id: str
    circuit: Path
    fault: Fault
    latent: bool


def holdout_cases(name: str) -> list[Case]:
    data = yaml.safe_load((SCENARIOS_DIR / HOLDOUT_FILES[name]).read_text(encoding="utf-8"))
    circuit = (SCENARIOS_DIR / data["circuit"]).resolve()
    return [Case(c["id"], circuit, Fault.from_dict(c), bool(c["latent"])) for c in data["cases"]]


def frozen_hashes() -> dict:
    """Fingerprints of what must not change between dev and clean runs."""
    from probeforge.agent import prompts
    from probeforge.baseline import halfsplit
    from probeforge.tools.toolbox import TOOL_SPECS

    def sha(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:12]

    return {
        "prompt": sha(inspect.getsource(prompts) + json.dumps(TOOL_SPECS, sort_keys=True)),
        "baseline": sha(inspect.getsource(halfsplit)),
        "image_only_prompt_edits": sha(json.dumps(IMAGE_ONLY_PROMPT_EDITS)),  # applied only with --no-netlist
    }


def build_cases(suite: str) -> list[Case]:
    cases = []
    if suite in ("scenarios", "all"):
        cases += [Case(s.id, s.circuit, s.fault, False) for s in load_scenarios()]
    if suite in ("dev", "all"):
        cases += holdout_cases("dev")
    if suite == "clean":
        cases += holdout_cases("clean")
    return cases


def evidence_counts(diagnosis: dict | None) -> tuple[int, int]:
    ev = (diagnosis or {}).get("evidence") or []
    return (sum(e.get("type") == "functional_test" for e in ev), sum(e.get("type") == "instrument_reading" for e in ev))


def run_case(case: Case, args, client, out_dir: Path, rep: int, ledger: SpendLedger | None) -> dict:
    circuit = Circuit.load(case.circuit)
    circuit.apply_fault(case.fault)
    circuit.set_power(True)
    t0 = time.perf_counter()
    name = case.id if args.repeat == 1 else f"{case.id}_r{rep}"
    approver = approve_all if args.approve else deny_all
    if args.runner == "agent":
        run, tb = run_agent(circuit, client, model=args.model, effort=args.effort, max_turns=args.max_turns,
                            approver=approver, include_image=not args.no_image,
                            include_netlist=not args.no_netlist)
        diagnosis, outcome, notes = run.diagnosis, run.outcome, []
        if ledger:
            ledger.record(run.cost_usd, f"{out_dir.name}/{name}")
    elif args.runner == "hybrid":
        true_netlist, true_data = circuit.netlist, yaml.safe_load(case.circuit.read_text(encoding="utf-8"))
        h = run_hybrid(circuit, client, hybrid_model(args.transcription), schematic_png(case.circuit), approver=approver,
                       repair=not args.no_repair, do_explain=not args.no_explain,
                       true_netlist=true_netlist, true_data=true_data)
        diagnosis, outcome, run, tb, notes = h.diagnosis, h.outcome, h.usage, h.planner.tb, h.planner.notes
        hybrid_extra = {**h.trace_extra(), "transcription": args.transcription, "conflicts": h.planner.conflicts}
        if ledger:
            ledger.record(run.cost_usd, f"{out_dir.name}/{name}")
    else:
        baseline = (HalfSplitBaseline if args.runner == "baseline" else InfoGainBaseline)(circuit, approver=approver)
        diagnosis, run = baseline.run(), None
        tb, outcome, notes = baseline.tb, diagnosis.get("outcome"), baseline.notes
    seconds = time.perf_counter() - t0
    trace = make_trace(case=name, runner=args.runner, tb=tb, diagnosis=diagnosis, outcome=outcome, seconds=seconds,
                       run=run, notes=notes, extra={"approve": args.approve,
                                                    **(hybrid_extra if args.runner == "hybrid" else {})})
    (out_dir / f"{name}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    error = trace["error"]
    tokens, cost, turns = trace["tokens"], trace["cost_usd"], trace["turns"]
    protocol_errors, recovered = trace["protocol_errors"], trace["recovered_text_calls"]
    missing = trace["missing_hypothesis_updates"]
    seconds = trace["seconds"]

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
        "protocol_errors": protocol_errors, "recovered_text_calls": recovered, "missing_hypothesis_updates": missing,
        "approval_requests": tb.policy.stats.approval_requests,
        "evidence_functional": func, "evidence_instrument": inst,
        "tokens": tokens["prompt"] + tokens["completion"], "cost_usd": cost, "seconds": seconds, "error": error,
        **(hybrid_row(trace) if args.runner == "hybrid" else {}),
    }


_png_cache: dict = {}


def schematic_png(circuit_path: Path) -> bytes:
    """The schematic image of the real circuit, as given to the hybrid pipeline (rendered once)."""
    if circuit_path not in _png_cache:
        _png_cache[circuit_path] = render_png(Netlist.load(circuit_path))
    return _png_cache[circuit_path]


def hybrid_model(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def hybrid_summary(rows: list[dict]) -> str:
    n = len(rows)
    return "\n".join([
        "", "**Verify step**", "",
        f"- Cases with a reading that contradicted every candidate: {sum(r['conflicts'] > 0 for r in rows)}/{n} "
        f"({sum(r['conflicts'] for r in rows)} conflicts)",
        f"- Netlist corrections proposed: {sum(r['corrections'] for r in rows)}; resolved the conflict on replay: "
        f"{sum(r['corrections_resolved'] for r in rows)}; changed wiring: {sum(r['corrections_wiring_changed'] for r in rows)}; "
        f"every rewired net is a true net: {sum(r['corrections_wiring_ok'] for r in rows)}; "
        f"healthy panel sequence right after the correction: {sum(r['corrections_panel_right'] for r in rows)}",
        f"- Netlist exactly right at the end: {sum(r['netlist_right_at_end'] for r in rows)}/{n}; "
        f"handed over to a human (no consistent model): {sum(r['gave_up'] for r in rows)}",
        f"- Explanations citing at least one step: {sum(bool(r['cited_steps']) for r in rows)}/{n}", "",
    ])


def hybrid_row(trace: dict) -> dict:
    """Verify-step metrics for one case (the truth comparison is logged after each model answer)."""
    corr = trace["corrections"]
    truth = [c.get("truth") or {} for c in corr]
    return {
        "conflicts": trace["conflicts"], "corrections": len(corr),
        "corrections_resolved": sum(c.get("candidates_after_replay", 0) > 0 for c in corr),
        "corrections_wiring_ok": sum(bool(t.get("wiring_ok")) for t in truth),
        "corrections_wiring_changed": sum(t.get("nets_added", 0) > 0 for t in truth),
        "corrections_panel_right": sum(t.get("panel_steps_same") == t.get("panel_steps") for t in truth if t),
        "netlist_right_at_end": bool(truth and truth[-1].get("netlist_fully_right")),
        "gave_up": trace["gave_up"], "cited_steps": trace["cited_steps"],
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
        f"missing hypothesis updates: {sum(r['missing_hypothesis_updates'] for r in rows)}, "
        f"approval requests: {sum(r['approval_requests'] for r in rows)} (denied {sum(r['approvals_denied'] for r in rows)}), "
        f"errors: {sum(1 for r in rows if r['error'])}",
        f"- Tokens: {sum(r['tokens'] for r in rows)}, cost ${sum(r['cost_usd'] for r in rows):.3f} "
        f"(${sum(r['cost_usd'] for r in rows) / max(n, 1):.3f} per case)",
        f"- Time: {sum(r['seconds'] for r in rows):.0f} s summed over cases, {wall:.0f} s wall clock",
    ]
    return "\n".join(summary) + "\n\n" + "\n".join([header, *lines]) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", choices=["agent", "baseline", "infogain", "hybrid"], default="agent",
                    help="baseline = half-split; infogain = perfect-model information-gain search; "
                         "hybrid = transcribed netlist + info-gain planner + Muse Spark repair and explanation")
    ap.add_argument("--transcription", default="scenarios/transcriptions/star_delta_run2.yaml",
                    help="hybrid: the transcribed netlist used as the model")
    ap.add_argument("--no-repair", action="store_true", help="hybrid: no netlist corrections (stop at a conflict)")
    ap.add_argument("--no-explain", action="store_true", help="hybrid: skip the technician explanation")
    ap.add_argument("--suite", choices=["scenarios", "dev", "clean", "all"], default="scenarios")
    ap.add_argument("--approve", action="store_true", help="simulated human approves reset / re-power requests")
    ap.add_argument("--model", default=MUSE_SPARK)
    ap.add_argument("--effort", default=None, help="reasoning_effort: minimal, low, medium, high, xhigh")
    ap.add_argument("--only", nargs="*", default=None, help="case ids, e.g. s01 h05")
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true", help="run even if the spend limit would be exceeded")
    ap.add_argument("--no-image", action="store_true", help="ablation: netlist only, no schematic image")
    ap.add_argument("--no-netlist", action="store_true", help="ablation: schematic image only, no text netlist")
    args = ap.parse_args()

    cases = [c for c in build_cases(args.suite) if not args.only or c.id in args.only]
    jobs = [(c, rep) for rep in range(1, args.repeat + 1) for c in cases]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = (f"{stamp}_{args.runner}_{args.suite}" + (f"_{args.effort or 'default'}" if args.runner == "agent" else "")
           + ("_approve" if args.approve else "") + ("_noimage" if args.no_image else "") + ("_nonetlist" if args.no_netlist else "")
           + ("_norepair" if args.runner == "hybrid" and args.no_repair else ""))
    out_dir = ROOT / "runs" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    client, ledger = None, None
    if args.runner in ("agent", "hybrid"):
        ledger = SpendLedger()
        try:
            ledger.check(len(jobs) * EST_PER_AGENT_RUN_USD, force=args.force, what=f"{len(jobs)} agent runs")
        except SpendLimitError as e:
            raise SystemExit(f"Refusing to start: {e}")
        client = make_client()

    started = time.perf_counter()

    def job(item):
        case, rep = item
        row = run_case(case, args, client, out_dir, rep, ledger)
        print(f"{row['case']}: {row['diagnosed']} (expected {row['expected']}) correct={yes(row['correct'])} "
              f"meas={row['measurements']} {row['seconds']}s" + (f" ERROR {row['error']}" if row["error"] else ""), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows = list(pool.map(job, jobs))
    wall = time.perf_counter() - started

    who = {"agent": f"{args.model}, effort {args.effort or 'default'}", "baseline": "half-split baseline",
           "infogain": "information-gain baseline (perfect fault model)",
           "hybrid": f"transcription {args.transcription}, " + ("no repair" if args.no_repair else f"repair by {MUSE_SPARK}")}[args.runner]
    who += ", approvals granted" if args.approve else ", approvals denied"
    table = render(rows, f"{args.runner} on {args.suite} ({who}), {len(rows)} runs", wall)
    if args.runner == "hybrid":
        table += hybrid_summary(rows)
    print("\n" + table)
    (out_dir / "results.md").write_text(table, encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps({"args": vars(args), "frozen": frozen_hashes(), "wall_s": wall, "rows": rows}, indent=2), encoding="utf-8")
    print(f"Frozen: {frozen_hashes()}")
    if ledger:
        print(f"Spend: ${ledger.total:.2f} of ${ledger.limit_usd:.2f}")
    print(f"Traces: {out_dir}")


if __name__ == "__main__":
    main()
