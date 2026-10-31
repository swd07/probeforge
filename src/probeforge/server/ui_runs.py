"""Local list of the faults run in the UI (decision D44): bench, mode, fault, how the run ended and when, appended once
per session after the run ends (diagnosis in, stopped, replaced by a new run, or the browser left). It lives in the
git-ignored runs/ folder, is never sent to the agent or the planner, and serves one purpose: every fault seen in the
UI before a holdout run is excluded from the holdout pool (S5 exclusion (c)).
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_lock = threading.Lock()


def path() -> Path:
    return Path(os.environ.get("PROBEFORGE_UI_RUNS") or ROOT / "runs" / "ui_runs.jsonl")


def record(session, ended: str) -> None:
    """Append the session's fault once; later calls for the same session do nothing."""
    if session is None or getattr(session, "_ui_run_recorded", False):
        return
    session._ui_run_recorded = True
    faults = getattr(session, "faults", None) or [session.fault]
    row = {"when": datetime.now().isoformat(timespec="seconds"), "bench": getattr(session, "bench_name", "star_delta"),
           "mode": session.mode, "faults": [str(f) for f in faults], "source": session.source, "ended": ended}
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock, p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def faults_run(bench: str = "ats") -> list[dict]:
    """Every recorded UI run on this bench (empty if the file does not exist)."""
    p = path()
    if not p.exists():
        return []
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if r["bench"] == bench]
