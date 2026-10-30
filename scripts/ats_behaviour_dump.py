"""Record the observable behaviour of the ATS bench for every catalog fault plus the healthy case, to prove that a
bench change (time step, fault lookup) changes nothing observable.

  python -m uv run python scripts/ats_behaviour_dump.py out.json
  python -m uv run python scripts/ats_behaviour_dump.py --compare before.json after.json

Per case: the twin-check signature (panel, display, alarms, metering and event log with causes at 2, 5, 15, 30 and 60 s
after the outage; every accessible voltage; every resistance isolated; the manual operation check), and the full
outage and retransfer timeline (event log with times, final position and lights, UPS time left).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from probeforge.ats import AtsBench  # noqa: E402
from probeforge.ats.ambiguity import signature  # noqa: E402
from probeforge.ats.faults import all_faults  # noqa: E402


def timeline(faults) -> dict:
    b = AtsBench(faults=faults)
    b.lose_utility()
    b.step(60)
    b.restore_utility()
    b.step(b.s["t_3a"] + b.s["t_2e"] + 30)
    i = b.indicators()
    return {"events": i["events"], "position": b.position, "lights": i["lights"], "ups_left": i["ups"]["left_s"],
            "coil_burnt": b.coil_burnt, "time": i["time_s"]}


def dump() -> dict:
    out = {}
    for f in [None] + all_faults(AtsBench().n):
        fs = [f] if f else []
        out[str(f) if f else "healthy"] = {"signature": json.loads(json.dumps(signature(fs), default=str)),
                                           "timeline": timeline(fs)}
    return out


def main() -> None:
    if sys.argv[1] == "--compare":
        a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:4])
        diff = [k for k in a if a[k] != b.get(k)]
        print(f"{len(a)} cases compared; {len(diff)} differ" + (f": {diff[:10]}" if diff else ": identical"))
        sys.exit(1 if diff or set(a) != set(b) else 0)
    Path(sys.argv[1]).write_text(json.dumps(dump()), encoding="utf-8")
    print(f"written {sys.argv[1]}")


if __name__ == "__main__":
    main()
