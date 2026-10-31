"""Gate for the next-reading display: runs with and without the UI helper must be identical (no API calls).

  python -m uv run python scripts/ats_nextstep_identity.py                      (12 dev cases, baseline and saved models)

For every dev case and model (the info-gain baseline on the true netlist, and the frozen Hybrid v2 on each saved
transcription, no explanation, no repair): run once without an update hook and once with a hook that calls
probeforge.ats.nextstep.planned_next. The full tool log (every call, argument and result) and the diagnosis must be
identical, and every plan shown must be the step the run then took. Exit code 1 on any difference.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_ats import load_cases, scenario_bench  # noqa: E402

from probeforge.ats import AtsBench  # noqa: E402
from probeforge.ats.hybrid.pipeline import run_ats_hybrid, warm  # noqa: E402
from probeforge.ats.infogain import AtsInfoGain  # noqa: E402
from probeforge.ats.nextstep import planned_next  # noqa: E402
from probeforge.ats.transcriptions import DIR, from_run, load  # noqa: E402


def dump(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


def run(kind: str, t: dict | None, case: dict, hook: bool):
    plans: list[tuple[int, dict]] = []

    def on_update(planner, step):
        plans.append((len(planner.tb.log), planned_next(planner)))

    bench = scenario_bench(case)
    if kind == "baseline":
        p = AtsInfoGain(bench, AtsBench().n, model_key="true", on_update=on_update if hook else None)
        d = p.run()
    else:
        r = run_ats_hybrid(bench, None, t["data"], t["raw"], [], flags=t["flags"], repair=False, do_explain=False,
                           healthy=t["healthy"], on_update=on_update if hook else None)
        p, d = r.planner, r.diagnosis
    return p.tb.log, d, plans


def taken_after(log: list[dict], at: int) -> dict | None:
    return next((e for e in log[at:] if e["tool"] != "update_hypotheses"), None)


def main() -> None:
    models: list[tuple[str, dict | None]] = [("baseline", None)]
    sources = sys.argv[1:] or [p.stem for p in sorted(DIR.glob("*.yaml"))]
    for s in sources:
        models.append((s, from_run(ROOT / s) if (ROOT / s).is_dir() else load(s)))
    cases = load_cases()
    failures, plans_checked = [], 0
    for name, t in models:
        if t is not None:
            t0 = time.perf_counter()
            warm(t["data"], t["flags"])
            print(f"{name}: candidates simulated in {time.perf_counter() - t0:.0f} s")
        for cid, case in cases.items():
            t0 = time.perf_counter()
            log_a, d_a, _ = run(name, t, case, hook=False)
            log_b, d_b, plans = run(name, t, case, hook=True)
            same = dump(log_a) == dump(log_b) and dump(d_a) == dump(d_b)
            bad_plans = []
            for at, plan in plans:
                nxt = taken_after(log_b, at)
                want = plan["tool"]
                ok = nxt is not None and nxt["tool"] == want and (
                    want not in ("measure_voltage", "measure_resistance", "manual_operation_check", "read_position_indicator")
                    or all(nxt["args"].get(k) == v for k, v in plan["args"].items()))
                plans_checked += 1
                if not ok:
                    bad_plans.append(f"after log entry {at}: planned {want} {plan['args']}, took "
                                     f"{nxt and nxt['tool']} {nxt and nxt['args']}")
            status = "identical" if same and not bad_plans else "DIFFERENT"
            print(f"  {name} {cid}: {status}, {len(log_b)} log entries, {len(plans)} plans, "
                  f"{d_b.get('outcome')} {d_b.get('component', '')} {d_b.get('part', '')} {d_b.get('failure_mode', '')} "
                  f"({time.perf_counter() - t0:.1f} s)")
            if not same:
                failures.append(f"{name} {cid}: log or diagnosis differs with the helper")
            failures += [f"{name} {cid}: {b}" for b in bad_plans]
    print(f"\n{len(models)} models x {len(cases)} cases, {plans_checked} plans checked against the step taken.")
    if failures:
        print("FAILED:\n" + "\n".join(failures))
        sys.exit(1)
    print("PASSED: identical tool logs and diagnoses with and without the helper; every plan was the step taken.")


if __name__ == "__main__":
    main()
