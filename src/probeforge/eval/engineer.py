"""Engineer reference traces recorded in manual mode (scenarios/engineer_traces/*.json).

Each file is a run trace in the same format as agent runs, plus the fault it was
recorded on and the engineer's name. They form the "engineer" column next to the
agent and the baseline.
"""

import json
from pathlib import Path

from probeforge.faults import Fault
from probeforge.faults.catalog import SCENARIOS_DIR

ENGINEER_DIR = SCENARIOS_DIR / "engineer_traces"


def load_engineer_traces(directory: Path = ENGINEER_DIR) -> dict[Fault, list[dict]]:
    traces: dict[Fault, list[dict]] = {}
    for path in sorted(Path(directory).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("runner") != "human" or "fault" not in data:
            continue
        data["file"] = path.name
        traces.setdefault(Fault.from_dict(data["fault"]), []).append(data)
    return traces


def engineer_reference(fault: Fault, traces: dict[Fault, list[dict]] | None = None) -> dict | None:
    """Most recent engineer trace for a fault, as a compact column."""
    traces = load_engineer_traces() if traces is None else traces
    runs = traces.get(fault)
    if not runs:
        return None
    t = max(runs, key=lambda r: r.get("recorded", ""))
    return {
        "engineer": t.get("engineer"),
        "verdict": t.get("verdict"),
        "measurements": t["measurements"],
        "redundant": t["redundant_measurements"],
        "blocked": t["policy"]["blocked"],
        "seconds": t["seconds"],
        "runs": len(runs),
        "file": t["file"],
    }
