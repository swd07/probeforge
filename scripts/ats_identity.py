"""Offline identity proof for changes to frozen ATS code (decision D47): Hybrid v2 (both saved transcriptions) and the
info-gain baseline on the 12 dev cases and the 28 holdout cases, without model calls. Every tool log and diagnosis is
hashed; two records are compared case by case. The holdout cases are also compared with the traces recorded in the
holdout run itself (results/runs/20261031_123544_ats_holdout), for the default transcription and the baseline.

  python -m uv run python scripts/ats_identity.py --out results/identity/before.json
  python -m uv run python scripts/ats_identity.py --compare results/identity/before.json results/identity/after.json

The agent is not covered: it needs model calls (it is not re-run).
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_ats import load_cases, scenario_bench  # noqa: E402

from probeforge.ats import AtsBench  # noqa: E402
from probeforge.ats.freeze import ats_frozen_hashes  # noqa: E402
from probeforge.ats.hybrid.pipeline import healthy_sequence, run_ats_hybrid, warm  # noqa: E402
from probeforge.ats.hybrid.read import to_netlist  # noqa: E402
from probeforge.ats.infogain import AtsInfoGain  # noqa: E402
from probeforge.ats.transcriptions import DEFAULT, DIR, load  # noqa: E402

HOLDOUT = ROOT / "scenarios" / "ats_holdout" / "holdout.yaml"
RUN = ROOT / "results" / "runs" / "20261031_123544_ats_holdout"


def canon(x):
    return json.loads(json.dumps(x, default=str))  # tuples as lists, as in the saved traces


def digest(x) -> str:
    return hashlib.sha256(json.dumps(canon(x), sort_keys=True).encode()).hexdigest()[:16]


def cases() -> dict[str, dict]:
    out = dict(load_cases())
    out.update({c["id"]: c for c in yaml.safe_load(HOLDOUT.read_text(encoding="utf-8"))["cases"]})
    return out


def record() -> dict:
    rows = {}
    cs = cases()
    for tid in [p.stem for p in sorted(DIR.glob("*.yaml"))]:
        t = load(tid)
        ok, events = healthy_sequence(to_netlist(t["data"]))
        warm(t["data"], t["flags"])
        for cid, case in cs.items():
            r = run_ats_hybrid(scenario_bench(case), None, t["data"], t["raw"], [], flags=t["flags"], repair=False,
                               do_explain=False, healthy={"ok": ok, "events": events})
            rows[f"hybrid/{tid}/{cid}"] = {"tool_log": digest(r.planner.tb.log), "diagnosis": digest(r.diagnosis)}
    true = AtsBench().n
    for cid, case in cs.items():
        p = AtsInfoGain(scenario_bench(case), true, model_key="true")
        d = p.run()
        rows[f"baseline/{cid}"] = {"tool_log": digest(p.tb.log), "diagnosis": digest(d)}
    return {"frozen": ats_frozen_hashes(), "rows": rows}


def recorded() -> dict:
    """The holdout run's own traces, hashed the same way."""
    out = {}
    for kind, key in (("hybrid", f"hybrid/{DEFAULT}"), ("baseline", "baseline")):
        for f in sorted((RUN / kind).glob("h*.json")):
            tr = json.loads(f.read_text(encoding="utf-8"))
            out[f"{key}/{f.stem}"] = {"tool_log": digest(tr["tool_log"]), "diagnosis": digest(tr["diagnosis"])}
    return out


def compare(a: dict, b: dict, label: str) -> list[str]:
    diff = [k for k in a if k not in b or a[k] != b[k]]
    print(f"{label}: {len(a) - len(diff)} of {len(a)} identical (tool log and diagnosis)"
          + ("" if not diff else f"; DIFFERENT: {diff}"))
    return diff


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--compare", nargs=2)
    args = ap.parse_args()
    if args.compare:
        a, b = (json.loads((ROOT / p).read_text(encoding="utf-8")) for p in args.compare)
        sys.exit(1 if compare(a["rows"], b["rows"], f"{args.compare[0]} vs {args.compare[1]}") else 0)
    rec = record()
    bad = compare(recorded(), rec["rows"], "holdout run traces vs this code")
    rec["vs_holdout_run"] = {"identical": not bad, "different": bad}
    if args.out:
        out = ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rec, indent=1, sort_keys=True), encoding="utf-8")
        print(f"{len(rec['rows'])} runs recorded to {args.out}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
