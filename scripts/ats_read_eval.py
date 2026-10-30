"""Hybrid v2 Read step on the ATS: read the drawing sheets N times, build the consensus model and score every read
against the true netlist (evaluation only: nothing scored here reaches the model).

  python -m uv run python scripts/ats_read_eval.py --reads 3

Writes runs/<timestamp>_ats_reads/: the raw compact transcriptions, the built netlists, the consensus model, scores.
"""

import argparse
import json
import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from probeforge.agent.client import make_client  # noqa: E402
from probeforge.ats import AtsBench  # noqa: E402
from probeforge.ats.hybrid.read import read_consensus  # noqa: E402
from probeforge.eval.spend import SpendLedger, SpendLimitError  # noqa: E402
from probeforge.hybrid.llm import Usage  # noqa: E402
from probeforge.hybrid.netlist_io import score_flags, wrong_nets  # noqa: E402

EST_PER_READ_USD = 0.06


def pairs(nets: dict) -> set[frozenset]:
    return {frozenset(p) for ts in nets.values() for p in combinations(sorted(set(map(str, ts))), 2)}


def prf(found: set, true: set) -> dict:
    tp = len(found & true)
    return {"found": len(found), "true": len(true), "matched": tp,
            "precision": round(tp / len(found), 3) if found else 0.0, "recall": round(tp / len(true), 3) if true else 0.0}


def score(data: dict, true) -> dict:
    parts = {f"{c}:{n}" for c, s in data["components"].items() for k, v in s.items() if isinstance(v, list) for n in v}
    true_parts = {p.id for p in true.parts.values()}
    wrong = wrong_nets(data, true)
    return {
        "components": prf(set(data["components"]), set(true.components)),
        "parts": prf(parts, true_parts),
        "parts_missing": sorted(true_parts - parts),
        "parts_extra": sorted(parts - true_parts),
        "connections": prf(pairs(data["nets"]), pairs(true.nets)),
        "nets_exact": {"matched": len(true.nets) - len(wrong), "true": len(true.nets)},
        "nets_wrong": wrong,
        "flags": score_flags(data.get("uncertain") or [], data, true),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reads", type=int, default=3)
    ap.add_argument("--effort", default="medium")
    args = ap.parse_args()
    ledger = SpendLedger()
    try:
        ledger.check(EST_PER_READ_USD * args.reads, what=f"{args.reads} ATS drawing reads")
    except SpendLimitError as e:
        sys.exit(str(e))
    out = ROOT / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}_ats_reads"
    out.mkdir(parents=True)
    usage = Usage(effort=args.effort)
    true = AtsBench().n
    try:
        model, flags, summary, raws = read_consensus(make_client(), usage, reads=args.reads, effort=args.effort)
    finally:
        ledger.record(usage.cost_usd, f"{out.name}/reads")
        (out / "turns.json").write_text(json.dumps(usage.turn_log, indent=2), encoding="utf-8")  # replies kept even on failure
    from probeforge.ats.hybrid.read import build

    report = {"summary": summary, "cost_usd": round(usage.cost_usd, 4), "tokens": usage.prompt_tokens + usage.completion_tokens,
              "reads": [], "consensus": score(model, true)}
    for i, raw in enumerate(raws):
        (out / f"read{i + 1}_raw.yaml").write_text(yaml.safe_dump(raw, sort_keys=False, width=200), encoding="utf-8")
        data = build(raw)
        report["reads"].append(score(data, true))
    (out / "consensus.yaml").write_text(yaml.safe_dump(model, sort_keys=False, width=200), encoding="utf-8")
    (out / "turns.json").write_text(json.dumps(usage.turn_log, indent=2), encoding="utf-8")
    (out / "score.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for i, r in enumerate(report["reads"] + [report["consensus"]]):
        name = f"read {i + 1}" if i < len(report["reads"]) else "consensus"
        c, p = r["connections"], r["parts"]
        print(f"{name}: components {r['components']['matched']}/{r['components']['true']}, parts P {p['precision']} R {p['recall']}, "
              f"connections P {c['precision']} R {c['recall']}, nets exact {r['nets_exact']['matched']}/{r['nets_exact']['true']}, "
              f"flags {r['flags']}")
    print(f"summary {summary}; cost ${usage.cost_usd:.3f}; written to {out}")


if __name__ == "__main__":
    main()
