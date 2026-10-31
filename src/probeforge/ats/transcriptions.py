"""Saved ATS transcriptions: the model step output of recorded Hybrid v2 runs (Muse Spark reads of the drawing-sheet
crops, the fault-free sequence check and the accepted repairs), kept in scenarios/transcriptions/ats/ so the UI and
the offline checks can run the frozen hybrid on a recorded model without API calls. Each file carries the run id and
date it was recorded in, the repair log and the read quality (evaluation only, never sent to the model). Only model
outputs are stored: no drawing image and nothing from the submittal cover pages
(scripts/export_ats_transcription.py checks this before a file is written).
"""

from pathlib import Path

import yaml

from probeforge.hybrid.netlist_io import flags_of

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "scenarios" / "transcriptions" / "ats"
DEFAULT = "run_20261031_003748"  # saved reads, two accepted repairs (shows the repair step)


def flags_from_versions(versions: list[dict]) -> list[dict]:
    """The wiring flags as prepare_model leaves them: each accepted repair's flags in front of the earlier ones."""
    out: list[dict] = []
    for v in versions:
        out = flags_of(v) + out
    return out


def from_run(run_dir: Path) -> dict:
    """A recorded hybrid run folder (runs/<stamp>_ats_hybrid) as a transcription record."""
    m = yaml.safe_load((run_dir / "model.yaml").read_text(encoding="utf-8"))
    versions = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((run_dir / "versions").glob("*.yaml"))]
    return {"data": m["data"], "raw": m["raw"], "flags": flags_from_versions(versions) if versions else flags_of(m["data"]),
            "healthy": m["healthy"], "read_quality": m.get("read_quality", []), "summary": m.get("summary", {})}


def available() -> list[dict]:
    out = []
    for p in sorted(DIR.glob("*.yaml")):
        t = yaml.safe_load(p.read_text(encoding="utf-8"))
        out.append({k: t.get(k) for k in ("id", "label", "run_id", "recorded", "reads", "repairs", "cost_usd")})
    return out


def load(tid: str = DEFAULT) -> dict:
    p = DIR / f"{tid}.yaml"
    if not p.is_file() or p.parent != DIR:
        raise KeyError(f"no saved transcription {tid!r}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))
