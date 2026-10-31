"""Export the model step of a recorded Hybrid v2 run to scenarios/transcriptions/ats/ (for the UI and offline checks).

  python -m uv run python scripts/export_ats_transcription.py runs/20261031_003748_ats_hybrid --label "..."

Writes model outputs only (the final model, the raw read it came from, the wiring flags, the fault-free sequence check
with the repair log, the read quality per version, costs from the run's turn logs), labelled with the run id and the
date. Privacy gate before writing: every word of the submittal cover page text (the only page with a text layer, read
locally from docs/vendor/) that also occurs in the export, and is not already public in this repo (our redrawing and
docs/ATS_MODEL.md), stops the export. The other submittal pages are images; the crops the model saw exclude them and
every title block (scripts/render_ats_sheets.py), and the export's free-text words are listed for a manual review
(--words).
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from probeforge.ats.transcriptions import DIR, from_run  # noqa: E402

PDF = ROOT / "docs" / "vendor" / "asco_978741_submittal.pdf"
PUBLIC = [ROOT / "scenarios" / "circuits" / "asco_300g_978741.yaml", ROOT / "docs" / "ATS_MODEL.md"]
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9&'.-]*[A-Za-z0-9]")


def words(text: str) -> set[str]:
    return {w.lower() for w in WORD.findall(text) if len(w) >= 3}


def cover_words() -> set[str]:
    import pymupdf

    doc = pymupdf.open(PDF)
    out = set()
    for page in doc:
        out |= words(page.get_text())
    return out


def privacy_hits(text: str) -> list[str]:
    public = set().union(*(words(p.read_text(encoding="utf-8")) for p in PUBLIC))
    return sorted((cover_words() - public) & words(text))


def costs(run_dir: Path, summary: dict) -> dict:
    turns = json.loads((run_dir / "model_turns.json").read_text(encoding="utf-8"))
    if summary.get("from"):  # the reads came from an earlier reads run
        turns = json.loads((ROOT / summary["from"] / "turns.json").read_text(encoding="utf-8")) + turns
    by = {}
    for t in turns:
        k = "reads" if t["purpose"].startswith("transcription") else t["purpose"]
        by[k] = round(by.get(k, 0.0) + t["cost_usd"], 4)
    return {"cost_usd": round(sum(t["cost_usd"] for t in turns), 4), "cost_by_step": by,
            "seconds": round(sum(t["latency_s"] for t in turns), 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--label", required=True)
    ap.add_argument("--words", action="store_true", help="print the export's free-text words for a manual review")
    args = ap.parse_args()
    run_dir = ROOT / args.run_dir
    stamp = run_dir.name.split("_ats_")[0]
    t = from_run(run_dir)
    record = {
        "id": f"run_{stamp}", "label": args.label, "run_id": run_dir.name,
        "recorded": datetime.strptime(stamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M"),
        "model": "muse-spark-1.3, reads and repairs at medium effort",
        "source": "Muse Spark reads of 7 drawing-sheet crops of drawing 978741 (no cover, outline or order pages, no "
                  "title blocks); built into a netlist by the frozen Hybrid v2 read step",
        "reads": t["summary"].get("reads"), "repairs": len([a for a in t["healthy"].get("attempts", []) if a.get("accepted")]),
        **costs(run_dir, t["summary"]),
        "disclosure": "The hybrid pipeline (crops, reading conventions, sequence checks, repair messages) was developed "
                      "on this one drawing. Read quality is scored against our redrawing, for evaluation only.",
        "summary": t["summary"], "healthy": t["healthy"], "read_quality": t["read_quality"],
        "flags": t["flags"], "data": t["data"], "raw": t["raw"],
    }
    text = yaml.safe_dump(record, sort_keys=False, width=200, allow_unicode=True)
    if not PDF.is_file():
        sys.exit("privacy gate: the submittal PDF is not available locally, nothing written")
    hits = privacy_hits(text)
    if hits:
        sys.exit(f"privacy gate: {len(hits)} cover-page words occur in the export, nothing written: {hits}")
    if args.words:
        common = set().union(*(words(p.read_text(encoding="utf-8")) for p in PUBLIC))
        print("free-text words not in the public redrawing or docs:", sorted(words(text) - common))
    DIR.mkdir(parents=True, exist_ok=True)
    out = DIR / f"{record['id']}.yaml"
    out.write_text(text, encoding="utf-8")
    print(f"privacy gate passed (0 cover-page words); written {out.relative_to(ROOT)}: {record['reads']} reads, "
          f"{record['repairs']} accepted repairs, ${record['cost_usd']:.3f}")


if __name__ == "__main__":
    main()
