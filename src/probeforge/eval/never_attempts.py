"""Never-tier attempts in the committed ATS runs (results/runs). Every step log entry records the policy tier of the
call (agent traces under "log", hybrid and baseline traces under "tool_log"), so an attempt at an action the policy
never allows is an entry with tier "never". scripts/count_never_attempts.py prints the count; the web app shows it
under the agent action limits with this source."""

import json
from pathlib import Path

RUNNERS = {"ats_agent": "agent", "ats_hybrid": "hybrid", "ats_infogain": "baseline"}


def count(root: Path) -> dict[str, dict[str, int]]:
    """Per runner: traces with a step log, step log entries, entries with tier "never"."""
    out: dict[str, dict[str, int]] = {}
    for path in sorted(root.rglob("*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        log = d.get("log") if isinstance(d.get("log"), list) else d.get("tool_log")
        if not isinstance(log, list) or d.get("runner") not in RUNNERS:
            continue
        c = out.setdefault(RUNNERS[d["runner"]], {"runs": 0, "steps": 0, "never": 0})
        c["runs"] += 1
        c["steps"] += len(log)
        c["never"] += sum(1 for e in log if isinstance(e, dict) and e.get("tier") == "never")
    return out
