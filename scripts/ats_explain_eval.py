"""Explanation check of Hybrid v2 on the 12 ATS dev cases (decision D41), and the identity proof for the change.

  python -m uv run python scripts/ats_explain_eval.py --tag before            (paid: about $0.06 to $0.15)
  python -m uv run python scripts/ats_explain_eval.py --offline --tag before  (free: tool logs and diagnoses only)

Paid mode: the hybrid on the default saved transcription (repair as in the reported runs, explanation at low effort),
every explanation scored by probeforge.ats.hybrid.explain.check_text (the action must name the diagnosed part or a
twin, by its kind, and no other part). Offline mode: both saved transcriptions, no explanation, hashes of every tool
log and diagnosis. Both write runs/<stamp>_ats_explain_<tag>/ with results.json (and results.md for paid runs);
--compare A B checks that two result folders have identical tool logs and diagnoses.
"""

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_ats import load_cases, scenario_bench  # noqa: E402

from probeforge.agent.client import make_client  # noqa: E402
from probeforge.ats.freeze import ats_frozen_hashes  # noqa: E402
from probeforge.ats.hybrid.explain import check_text, consequence_split, template  # noqa: E402
from probeforge.ats.hybrid.pipeline import healthy_sequence, run_ats_hybrid, warm  # noqa: E402
from probeforge.ats.hybrid.read import sheet_images, to_netlist  # noqa: E402
from probeforge.ats.transcriptions import DEFAULT, DIR, load  # noqa: E402
from probeforge.eval.spend import SpendLedger, SpendLimitError  # noqa: E402
from probeforge.hybrid.llm import Usage  # noqa: E402

EST_USD = 0.15


def digest(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()[:16]


def run_case(cid, case, t, healthy, client, images):
    usage = Usage(effort="medium")
    t0 = time.perf_counter()
    r = run_ats_hybrid(scenario_bench(case), client, t["data"], t["raw"], images, usage=usage, flags=t["flags"],
                       repair=client is not None and bool(images), do_explain=client is not None, healthy=healthy)
    row = {"case": cid, "tool_log": digest(r.planner.tb.log), "diagnosis": r.diagnosis, "diagnosis_hash": digest(r.diagnosis),
           "seconds": round(time.perf_counter() - t0, 1), "cost_usd": round(usage.cost_usd, 5)}
    if client is not None:
        row["explanation"] = r.explanation
        co, dmg = consequence_split(r.planner, r.diagnosis)
        row["consequences"], row["damaged"] = co + dmg, dmg
        row["problems"] = check_text(r.explanation, r.diagnosis, r.planner.models[0], consequences=co + dmg, damaged=dmg)
        row["problems_lenient"] = check_text(r.explanation, r.diagnosis, r.planner.models[0], strict=False,
                                             consequences=co + dmg, damaged=dmg)
        row["record"] = getattr(r, "explain_record", None)
        row["explain_calls"] = len([x for x in usage.turn_log if x["purpose"] == "explanation"])
    return row


def compare(a: Path, b: Path) -> None:
    ra = {(r.get("transcription", DEFAULT), r["case"]): r for r in json.loads((a / "results.json").read_text())["rows"]}
    rb = {(r.get("transcription", DEFAULT), r["case"]): r for r in json.loads((b / "results.json").read_text())["rows"]}
    diff = [k for k in ra if k not in rb or (ra[k]["tool_log"], ra[k]["diagnosis_hash"]) != (rb[k]["tool_log"], rb[k]["diagnosis_hash"])]
    print(f"{len(ra)} runs compared: {'identical tool logs and diagnoses' if not diff else f'DIFFERENT: {diff}'}")
    sys.exit(1 if diff else 0)


def rescore(d: Path) -> None:
    """Score saved explanations with the current check; the planners are rebuilt offline (the same tool logs, no
    repairs ran in these runs) for the consequential faults of each diagnosis."""
    t = load(DEFAULT)
    n = to_netlist(t["data"])
    ok, events = healthy_sequence(n)
    warm(t["data"], t["flags"])
    cases = load_cases()
    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    for r in res["rows"]:
        h = run_ats_hybrid(scenario_bench(cases[r["case"]]), None, t["data"], t["raw"], [], flags=t["flags"], repair=False,
                           do_explain=False, healthy={"ok": ok, "events": events})
        assert digest(h.planner.tb.log) == r["tool_log"], r["case"]
        co, dmg = consequence_split(h.planner, h.diagnosis)
        r["problems"] = check_text(r["explanation"], r["diagnosis"], n, consequences=co + dmg, damaged=dmg)
        r["problems_lenient"] = check_text(r["explanation"], r["diagnosis"], n, strict=False, consequences=co + dmg, damaged=dmg)
        if co or dmg:
            tpl = template(h.diagnosis, h.planner, n)
            print(f"  {r['case']} template: {tpl}\n    template check: "
                  f"{check_text(tpl, h.diagnosis, n, consequences=co + dmg, damaged=dmg) or 'pass'}")
        print(f"  {r['case']}: strict {'; '.join(r['problems']) or 'pass'} | lenient {'; '.join(r['problems_lenient']) or 'pass'}")
    print(f"strict {sum(bool(r['problems']) for r in res['rows'])} of {len(res['rows'])}, lenient "
          f"{sum(bool(r['problems_lenient']) for r in res['rows'])} of {len(res['rows'])}")
    (d / "rescored.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--compare", nargs=2)
    ap.add_argument("--rescore", help="score a results folder again with the current check (no API calls)")
    args = ap.parse_args()
    if args.compare:
        return compare(ROOT / args.compare[0], ROOT / args.compare[1])
    if args.rescore:
        return rescore(ROOT / args.rescore)
    cases = load_cases()
    out = ROOT / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}_ats_explain_{args.tag or 'run'}{'_offline' if args.offline else ''}"
    out.mkdir(parents=True)
    rows = []
    ids = [p.stem for p in sorted(DIR.glob("*.yaml"))] if args.offline else [DEFAULT]
    client, images, ledger = None, [], SpendLedger()
    if not args.offline:
        try:
            ledger.check(EST_USD, what="ATS explanation check on 12 dev cases")
        except SpendLimitError as e:
            sys.exit(str(e))
        client, images = make_client(), sheet_images()
    for tid in ids:
        t = load(tid)
        ok, events = healthy_sequence(to_netlist(t["data"]))
        warm(t["data"], t["flags"])
        with ThreadPoolExecutor(max_workers=1 if args.offline else 4) as ex:
            got = list(ex.map(lambda c: run_case(c, cases[c], t, {"ok": ok, "events": events}, client, images), cases))
        for r in got:
            r["transcription"] = tid
            if client is not None:
                ledger.record(r["cost_usd"], f"{out.name}/{r['case']}")
        rows += got
    result = {"tag": args.tag, "offline": args.offline, "frozen": ats_frozen_hashes(), "rows": rows}
    (out / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if not args.offline:
        bad = [r for r in rows if r["problems"]]
        lines = [f"# Explanation check, {args.tag} (12 dev cases, transcription {DEFAULT})", "",
                 f"Mismatches: strict {len(bad)} of {len(rows)}, lenient {len([r for r in rows if r['problems_lenient']])} of "
                 f"{len(rows)}; cost ${sum(r['cost_usd'] for r in rows):.3f}.", "",
                 "| Case | Diagnosis | Check (strict) | Check (lenient) | Explanation |", "|---|---|---|---|---|"]
        for r in rows:
            d = r["diagnosis"]
            said = f"{d.get('component', '')} {d.get('part', '')} {d.get('failure_mode', '')}" if d.get("outcome") == "diagnosed" else d.get("outcome")
            lines.append(f"| {r['case']} | {said} | {'; '.join(r['problems']) or 'pass'} | "
                         f"{'; '.join(r['problems_lenient']) or 'pass'} | {r['explanation'].replace('|', '/')} |")
        (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines[:3]))
        for r in rows:
            print(f"  {r['case']}: {'; '.join(r['problems']) or 'pass'}")
    print(f"written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
