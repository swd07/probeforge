"""Run Hybrid v2 (and the info-gain ceiling baseline) on ATS cases.

  python -m uv run python scripts/run_ats_hybrid.py --cases a1_coil_open b1_wire7_open --reads-from runs/<dir>_ats_reads
  python -m uv run python scripts/run_ats_hybrid.py --cases ... --reads 3          (new live reads)
  python -m uv run python scripts/run_ats_hybrid.py --cases ... --baseline          (info-gain on the true netlist, free)

The transcription (3 reads + consensus) and the Model step (fault-free sequence check with repair) are done once per
run and shared by every case; each case then plans on the prepared model, with repair on conflicts and an explanation.
Batch approver as for the agent (approval tier yes, strong approval no). Writes runs/<timestamp>_ats_hybrid/: one
trace per case (no fault inside), model.yaml, results.md and results.json (with the expected fault, for scoring only).
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ats_read_eval import pairs, prf, score  # noqa: E402
from run_ats import accepted_answers, case_faults, load_cases, scenario_bench, twins_of  # noqa: E402

from probeforge.agent.client import make_client  # noqa: E402
from probeforge.ats import AtsBench  # noqa: E402
from probeforge.ats.hybrid.pipeline import prepare_model, run_ats_hybrid  # noqa: E402
from probeforge.ats.hybrid.read import build, parse_reply, read_consensus, sheet_images  # noqa: E402
from probeforge.ats.infogain import AtsInfoGain  # noqa: E402
from probeforge.eval.scoring import grade  # noqa: E402
from probeforge.eval.spend import SpendLedger, SpendLimitError  # noqa: E402
from probeforge.eval.trace import make_trace  # noqa: E402
from probeforge.hybrid.consensus import consensus  # noqa: E402
from probeforge.hybrid.llm import Usage  # noqa: E402

EST_READ_USD, EST_CASE_USD = 0.11, 0.15


def saved_reads(d: Path) -> tuple[list[dict], list[dict]]:
    turns = json.loads((d / "turns.json").read_text(encoding="utf-8"))
    raws, datas = [], []
    for x in turns:
        if x["purpose"].startswith("transcription"):
            try:
                raw = parse_reply(x["text"])
                datas.append(build(raw))
                raws.append(raw)
            except Exception:  # noqa: BLE001 - unusable read left out, as live
                continue
    return raws, datas


def relay_contacts_of_data(data: dict) -> set[tuple]:
    """Controller relay contacts as (relay, terminals in either order, make or break)."""
    out = set()
    for c, s in data["components"].items():
        if s.get("type") == "relay":
            for key, kind in (("no_contacts", "contact_no"), ("nc_contacts", "contact_nc")):
                for part in s.get(key) or []:
                    out.add((c, tuple(sorted(str(part).split("-", 1))), kind))
    return out


def relay_contacts_of_netlist(n) -> set[tuple]:
    return {(p.component, tuple(sorted(p.name.split("-", 1))), p.kind) for p in n.parts.values()
            if p.kind in ("contact_no", "contact_nc")}


def read_quality(versions: list[dict], true) -> list[dict]:
    """Read quality of the transcription before repair, after each accepted repair and at the end, against the true
    netlist (evaluation only). An accepted repair that makes the connections worse is flagged."""
    keep = lambda ps: {p for p in ps if not any(t.startswith(("52U:", "NSD:")) for t in p)}  # noqa: E731
    true_relays = relay_contacts_of_netlist(true)
    out = []
    for i, data in enumerate(versions):
        s = score(data, true)
        w = prf(keep(pairs(data["nets"])), keep(pairs(true.nets)))
        rc = relay_contacts_of_data(data)
        q = {"version": "transcription" if i == 0 else f"after repair {i}", "parts_recall": s["parts"]["recall"],
             "connections_precision": s["connections"]["precision"], "connections_recall": s["connections"]["recall"],
             "no52u_precision": w["precision"], "no52u_recall": w["recall"],
             "nets_exact": f"{s['nets_exact']['matched']}/{s['nets_exact']['true']}",
             "relay_contacts_right": len(rc & true_relays), "relay_contacts_true": len(true_relays),
             "relay_contacts_wrong": sorted(f"{c} {'make' if k == 'contact_no' else 'break'} {'-'.join(ts)}"
                                           for c, ts, k in rc - true_relays)}
        if out:
            prev = out[-1]
            q["worse"] = (q["connections_precision"] < prev["connections_precision"]
                          or q["connections_recall"] < prev["connections_recall"]
                          or q["relay_contacts_right"] < prev["relay_contacts_right"]
                          or len(q["relay_contacts_wrong"]) > len(prev["relay_contacts_wrong"]))
        out.append(q)
    return out


def row(cid, case, d, outcome, tb, usage, seconds, extra) -> dict:
    answers = accepted_answers(case)
    twins = twins_of(case_faults(case), answers)
    dd = d if outcome == "diagnosed" else {"outcome": outcome}
    gs = [grade(dd, a, False, twins) for a in answers]
    g = next((x for x in gs if x["correct"]), gs[0])
    s = tb.policy.stats
    return {"case": cid, "family": case["family"], "expected": " or ".join(map(str, answers)),
            "diagnosed": f"{d.get('component', '')}:{d.get('part') or ''} {d.get('failure_mode', '')}".replace(": ", " ")
            if outcome == "diagnosed" else outcome, "confidence": d.get("confidence"), "note": d.get("note", ""),
            "correct": g["correct"], "justified": g["justified"], "confident_wrong": g["confident_wrong"],
            "measurements": tb.measurements, "policy_blocked": s.blocked, "approval_requests": s.approval_requests,
            "strong_approval_requests": s.strong_approval_requests, "approvals_denied": s.approvals_denied,
            "virtual_s": round(tb.bench.t - 60, 1), "model_calls": usage.turns if usage else 0,
            "tokens": (usage.prompt_tokens + usage.completion_tokens) if usage else 0,
            "cost_usd": round(usage.cost_usd, 4) if usage else 0.0, "seconds": round(seconds, 1), **extra}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", required=True)
    ap.add_argument("--reads", type=int, default=0, help="new live reads (0: use --reads-from)")
    ap.add_argument("--reads-from", default="", help="a runs/<dir>_ats_reads folder with saved reads")
    ap.add_argument("--baseline", action="store_true", help="info-gain on the true netlist instead (no API calls)")
    ap.add_argument("--no-repair", action="store_true")
    ap.add_argument("--no-explain", action="store_true")
    args = ap.parse_args()
    cases = load_cases()
    out = ROOT / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}_ats_{'baseline' if args.baseline else 'hybrid'}"
    out.mkdir(parents=True)
    rows = []
    if args.baseline:
        true = AtsBench().n
        for cid in args.cases:
            t0 = time.perf_counter()
            p = AtsInfoGain(scenario_bench(cases[cid]), true, model_key="true")
            d = p.run()
            rows.append(row(cid, cases[cid], d, d["outcome"], p.tb, None, time.perf_counter() - t0, {}))
            trace = make_trace(case=cid, runner="ats_infogain", tb=p.tb, diagnosis=d, outcome=d["outcome"],
                               seconds=time.perf_counter() - t0, notes=p.notes)
            (out / f"{cid}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        ledger = SpendLedger()
        est = EST_READ_USD * args.reads + 0.2 + EST_CASE_USD * len(args.cases)
        try:
            ledger.check(est, what=f"ATS hybrid run of {len(args.cases)} cases")
        except SpendLimitError as e:
            sys.exit(str(e))
        client, images, prep_usage = make_client(), sheet_images(), Usage(effort="medium")
        try:
            if args.reads:
                data, flags, summary, raws = read_consensus(client, prep_usage, images, reads=args.reads)
                raw = raws[summary["model_read"] - 1]
            else:
                raws, datas = saved_reads(ROOT / args.reads_from)
                data, extra, i = consensus(datas) if len(datas) > 1 else (datas[0], [], 0)
                raw, flags, summary = raws[i], data["uncertain"], {"reads": len(datas), "model_read": i + 1,
                                                                    "disagreement_regions": len(extra), "from": args.reads_from}
            data, raw, flags, healthy = prepare_model(client, prep_usage, data, raw, flags, images)
        finally:
            ledger.record(prep_usage.cost_usd, f"{out.name}/model")
            (out / "model_turns.json").write_text(json.dumps(prep_usage.turn_log, indent=2), encoding="utf-8")
        quality = read_quality(healthy["versions"], AtsBench().n)  # evaluation only: never sent to the model
        (out / "versions").mkdir()
        for k, v in enumerate(healthy["versions"]):  # every accepted model, for the record
            (out / "versions" / f"{k}_{'transcription' if k == 0 else f'after_repair_{k}'}.yaml").write_text(
                yaml.safe_dump(v, sort_keys=False, width=200), encoding="utf-8")
        (out / "model.yaml").write_text(yaml.safe_dump({"summary": summary, "healthy": {k: v for k, v in healthy.items()
                                                       if k != "versions"}, "read_quality": quality, "raw": raw, "data": data},
                                                       sort_keys=False, width=200), encoding="utf-8")
        for q in quality:
            print(f"read quality {q['version']}: parts R {q['parts_recall']}, connections P {q['connections_precision']} "
                  f"R {q['connections_recall']} (without 52U: P {q['no52u_precision']} R {q['no52u_recall']}), nets exact "
                  f"{q['nets_exact']}, relay contacts right {q['relay_contacts_right']}/{q['relay_contacts_true']} "
                  f"(wrong: {q['relay_contacts_wrong']}){'  WORSE THAN BEFORE THIS REPAIR' if q.get('worse') else ''}")
        print(f"model: {summary}; fault-free sequence ok: {healthy['ok']} ({len(healthy['attempts'])} repair attempts); "
              f"model cost ${prep_usage.cost_usd:.3f}")
        for cid in args.cases:
            usage = Usage(effort="medium")
            t0 = time.perf_counter()
            try:
                r = run_ats_hybrid(scenario_bench(cases[cid]), client, data, raw, images, usage=usage, flags=flags,
                                   repair=not args.no_repair, do_explain=not args.no_explain, healthy=healthy)
            finally:
                ledger.record(usage.cost_usd, f"{out.name}/{cid}")
            p = r.planner
            rows.append(row(cid, cases[cid], r.diagnosis, r.outcome, p.tb, usage, time.perf_counter() - t0,
                            {"corrections": len([c for c in r.corrections if not c.get("rejected")]),
                             "rejected": len([c for c in r.corrections if c.get("rejected")]), "variants": r.variants}))
            trace = make_trace(case=cid, runner="ats_hybrid", tb=p.tb, diagnosis=r.diagnosis, outcome=r.outcome,
                               seconds=r.seconds, run=usage, notes=p.notes,
                               extra={"explanation": r.explanation, "corrections": r.corrections, "healthy": healthy})
            (out / f"{cid}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{cid}: {rows[-1]['diagnosed']} correct={rows[-1]['correct']} meas={rows[-1]['measurements']} "
                  f"repairs={rows[-1]['corrections']}/{rows[-1]['rejected']} rejected ${rows[-1]['cost_usd']:.3f}")
    head = "| Case | Expected | Diagnosis | Correct | Confidently wrong | Meas. | Approval / strong (denied) | Cost |\n|---|---|---|---|---|---|---|---|"
    lines = [f"| {r['case']} | {r['expected']} | {r['diagnosed']} | {'yes' if r['correct'] else 'justified' if r['justified'] else 'no'} | "
             f"{'yes' if r['confident_wrong'] else 'no'} | {r['measurements']} | {r['approval_requests']} / "
             f"{r['strong_approval_requests']} ({r['approvals_denied']}) | ${r['cost_usd']:.3f} |" for r in rows]
    disclosure = ("" if args.baseline else
                  "Disclosure: the hybrid pipeline (drawing crops, reading conventions, the fault-free sequence checks "
                  "and the repair messages) was developed on this one drawing, after seeing the errors of these reads. "
                  "Generalization to other drawings is not shown.\n\n")
    md = (f"# ATS {'info-gain baseline (true netlist)' if args.baseline else 'Hybrid v2'} (dev cases, not holdout)\n\n"
          + disclosure + head
          + "\n" + "\n".join(lines) + f"\n\nCorrect {sum(r['correct'] for r in rows)}/{len(rows)}; confidently wrong "
          f"{sum(r['confident_wrong'] for r in rows)}; cost ${sum(r['cost_usd'] for r in rows):.3f}.\n")
    (out / "results.md").write_text(md, encoding="utf-8")
    (out / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(md)
    print(f"written to {out}")


if __name__ == "__main__":
    main()
