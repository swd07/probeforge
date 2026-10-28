"""Calibration of the agent's stated confidence, from every saved agent run.

Usage:  uv run python scripts/calibration.py [OUT.md]

Reads runs/*/results.json, keeps agent runs (not the baselines), keeps submitted diagnoses
(insufficient_information carries no claim to be right), and buckets them by stated confidence:
below 70%, 70 to 90%, 90% and above. A diagnosis counts as correct at pole level (component,
failure mode and part match the injected fault; probeforge.eval.scoring), rescored from the saved
diagnosis so old runs use the same definition. UI sessions are not saved as batch results and are
not included.
"""

import json
import sys
from pathlib import Path

from probeforge.eval.scoring import parse_fault, score

ROOT = Path(__file__).resolve().parents[1]
BUCKETS = [("below 70%", 0.0, 0.7), ("70 to 90%", 0.7, 0.9), ("90% and above", 0.9, 1.01)]
NOT_DIAGNOSED = {"insufficient_information", "no_diagnosis", "error"}


def agent_rows(run_dir: Path) -> list[dict]:
    data = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    runner = (data.get("args") or {}).get("runner", "agent")  # the first runs predate the runner field
    if runner != "agent" or "rows" not in data:  # baselines, hybrid, transcription tests
        return []
    rows = []
    for r in data["rows"]:
        outcome = r.get("outcome") or ("diagnosed" if r.get("diagnosed") not in NOT_DIAGNOSED else r.get("diagnosed"))
        if outcome != "diagnosed" or not isinstance(r.get("confidence"), (int, float)):
            continue
        case = r.get("case") or r["scenario"]  # the first runs called it scenario
        trace = json.loads((run_dir / f"{case}.json").read_text(encoding="utf-8"))
        s = score(trace["diagnosis"], parse_fault(r["expected"]))
        correct = s["component_ok"] and s["mode_ok"] and s["part_ok"]
        rows.append({"run": run_dir.name, "confidence": float(r["confidence"]), "correct": bool(correct)})
    return rows


def table(rows: list[dict]) -> list[str]:
    out = ["| Stated confidence | Diagnoses | Correct | Accuracy | Mean stated confidence |", "|---|---|---|---|---|"]
    for name, lo, hi in BUCKETS:
        b = [r for r in rows if lo <= r["confidence"] < hi]
        if not b:
            out.append(f"| {name} | 0 | - | - | - |")
            continue
        acc = sum(r["correct"] for r in b) / len(b)
        mean = sum(r["confidence"] for r in b) / len(b)
        out.append(f"| {name} | {len(b)} | {sum(r['correct'] for r in b)} | {acc:.0%} | {mean:.0%} |")
    n = len(rows)
    out.append(f"| all | {n} | {sum(r['correct'] for r in rows)} | {sum(r['correct'] for r in rows) / max(n, 1):.0%} | "
               f"{sum(r['confidence'] for r in rows) / max(n, 1):.0%} |")
    return out


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "results" / "2026-10-28_calibration.md"
    runs = sorted(p.parent for p in (ROOT / "runs").glob("*/results.json"))
    all_rows = [r for d in runs for r in agent_rows(d)]
    clean = [r for r in all_rows if "_clean_" in r["run"] and "noimage" not in r["run"]]
    used = sorted({r["run"] for r in all_rows})
    lines = [
        "# Confidence calibration (2026-10-28)",
        "",
        "Every submitted agent diagnosis in the saved batch runs, bucketed by the confidence the agent stated in",
        "submit_diagnosis. Correct = pole level: component, failure mode and part match the injected fault (rescored",
        "from the saved diagnoses, so every run uses the same definition). insufficient_information",
        "answers are left out (no claim). Each run of a repeated case counts separately.",
        "",
        "## All agent runs (dev and clean, muse-spark-1.3)",
        "",
        *table(all_rows),
        "",
        "## Clean holdout runs only (with the schematic image)",
        "",
        *table(clean),
        "",
        f"Runs used ({len(used)}): " + ", ".join(used),
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
