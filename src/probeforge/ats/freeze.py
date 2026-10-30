"""Fingerprints of the ATS components that must not change between dev and the holdout run (see DECISIONS.md D34).

Hybrid v2 is frozen on 2026-10-31: the read step (prompt included), the pipeline (sequence checks, repair, acceptance),
the information-gain planner (also the ceiling baseline) and the drawing crops. A test pins these values; changing a
fingerprinted component needs the user's approval first. The relay-panel fingerprints stay in scripts/run_scenarios.py.
"""

import hashlib
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _sha(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode()).hexdigest()[:12]  # same on a CRLF checkout


def ats_frozen_hashes() -> dict:
    from probeforge.ats import infogain
    from probeforge.ats.hybrid import pipeline, read

    crops = (ROOT / "scripts" / "render_ats_sheets.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    sheets = crops[crops.index("SHEETS = ["):crops.index("]\n\n\ndef main")]
    return {
        "ats_hybrid_read": _sha(inspect.getsource(read)),
        "ats_hybrid_pipeline": _sha(inspect.getsource(pipeline)),
        "ats_infogain": _sha(inspect.getsource(infogain)),
        "ats_sheet_crops": _sha(sheets),
    }
