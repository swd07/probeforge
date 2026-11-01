"""Fingerprints of the ATS components that must not change between dev and the holdout run (see DECISIONS.md D34).

Hybrid v2 is frozen on 2026-10-31: the read step (prompt included), the pipeline (sequence checks, repair, acceptance),
the information-gain planner (also the ceiling baseline) and the drawing crops. The explanation step was replaced on
2026-10-31 (D41: structured input, checked output; D42: consequential faults); tool logs and diagnoses were shown
unchanged. S5 freeze (2026-10-31, D45) adds everything else the holdout run depends on: the agent (its module, prompts,
the shared loop it imports, tools, policy), the bench and its circuit, the fault catalog and twin check, the scoring,
and the default saved transcription the hybrid runs on. A test pins these values; changing a fingerprinted component
needs the user's approval first. Post-holdout fixes (2026-11-01, D47): the toolbox, the policy and the explanation
step changed after the holdout run (the code of that run is the tag holdout-2026-10-31); the offline proof showed the
hybrid's and the baseline's tool logs and diagnoses unchanged. The relay-panel fingerprints stay in
scripts/run_scenarios.py.
"""

import hashlib
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _sha(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode()).hexdigest()[:12]  # same on a CRLF checkout


def ats_frozen_hashes() -> dict:
    from probeforge.agent import loop
    from probeforge.ats import agent, ambiguity, bench, faults, infogain, policy, prompts, tools
    from probeforge.ats.hybrid import explain, pipeline, read
    from probeforge.ats.transcriptions import DEFAULT, DIR
    from probeforge.eval import scoring

    crops = (ROOT / "scripts" / "render_ats_sheets.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    sheets = crops[crops.index("SHEETS = ["):crops.index("]\n\n\ndef main")]
    return {
        "ats_hybrid_read": _sha(inspect.getsource(read)),
        "ats_hybrid_pipeline": _sha(inspect.getsource(pipeline)),
        "ats_hybrid_explain": _sha(inspect.getsource(explain)),
        "ats_infogain": _sha(inspect.getsource(infogain)),
        "ats_sheet_crops": _sha(sheets),
        # S5 freeze (D45)
        "ats_agent": _sha(inspect.getsource(agent) + inspect.getsource(prompts)),
        "ats_agent_loop": _sha(inspect.getsource(loop)),
        "ats_tools": _sha(inspect.getsource(tools)),
        "ats_policy": _sha(inspect.getsource(policy)),
        "ats_bench": _sha(inspect.getsource(bench)
                          + (ROOT / "scenarios" / "circuits" / "asco_300g_978741.yaml").read_text(encoding="utf-8")),
        "ats_faults": _sha(inspect.getsource(faults) + inspect.getsource(ambiguity)),
        "ats_scoring": _sha(inspect.getsource(scoring)),
        "ats_transcription_default": _sha(DEFAULT + (DIR / f"{DEFAULT}.yaml").read_text(encoding="utf-8")),
    }
