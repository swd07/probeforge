"""ATS results, dev and S5 holdout side by side (docs/results/ats_results.md and .json).

  python -m uv run python scripts/ats_results.py results/runs/20261031_123544_ats_holdout   (regenerates docs/results/ats_results.json)

Dev columns (12 dev cases, never presented as holdout):
- agent: results/runs/20261031_012952_ats_agent_chat_low (Chat, low; the reported dev run, D38), recorded before the
  load-lost fields (D43), so no UPS at diagnosis;
- Hybrid v2: results/runs/20261031_114432_ats_explain_d42_after2 (default saved transcription, repair and explanation, the
  frozen code) for diagnoses, explanation checks and cost; readings, approvals, UPS and virtual time from a free
  replay of the same cases without model calls, whose tool logs and diagnoses were shown identical to the paid runs
  (D41, D43); wall time is not available for that run;
- info-gain baseline (true netlist, no model): run here, free, frozen code.
No API calls.
"""

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_ats import load_cases, scenario_bench  # noqa: E402
from run_ats_hybrid import row as hybrid_row  # noqa: E402

from probeforge.ats import AtsBench  # noqa: E402
from probeforge.ats.hybrid.pipeline import healthy_sequence, run_ats_hybrid, warm  # noqa: E402
from probeforge.ats.hybrid.read import to_netlist  # noqa: E402
from probeforge.ats.infogain import AtsInfoGain  # noqa: E402
from probeforge.ats.transcriptions import DEFAULT, load  # noqa: E402

RUNS = ROOT / "results" / "runs"  # the committed copies of the cited runs
DEV_AGENT = RUNS / "20261031_012952_ats_agent_chat_low"
DEV_HYBRID = RUNS / "20261031_114432_ats_explain_d42_after2"
OUT_JSON = ROOT / "docs" / "results" / "ats_results.json"


def dev_rows() -> dict[str, list[dict]]:
    cases = load_cases()
    agent = json.loads((DEV_AGENT / "results.json").read_text(encoding="utf-8"))
    paid = {r["case"]: r for r in json.loads((DEV_HYBRID / "results.json").read_text(encoding="utf-8"))["rows"]}
    t = load(DEFAULT)
    ok, events = healthy_sequence(to_netlist(t["data"]))
    warm(t["data"], t["flags"])
    hybrid, baseline = [], []
    true = AtsBench().n
    for cid, case in cases.items():
        r = run_ats_hybrid(scenario_bench(case), None, t["data"], t["raw"], [], flags=t["flags"], repair=False,
                           do_explain=False, healthy={"ok": ok, "events": events})
        p = paid[cid]
        if r.diagnosis != p["diagnosis"]:
            sys.exit(f"replay of {cid} differs from the paid dev run")
        h = hybrid_row(cid, case, r.diagnosis, r.outcome, r.planner.tb, None, 0.0,
                       {"explain_problems": p["problems"], "seconds": None})
        h["cost_usd"] = p["cost_usd"]
        h["uncached_cost_usd"] = None  # the explanation runs did not keep token counts per row
        hybrid.append(h)
        t0 = time.perf_counter()
        b = AtsInfoGain(scenario_bench(case), true, model_key="true")
        d = b.run()
        baseline.append(hybrid_row(cid, case, d, d["outcome"], b.tb, None, time.perf_counter() - t0, {"uncached_cost_usd": 0.0}))
    return {"agent": agent, "hybrid": hybrid, "baseline": baseline}


def holdout_rows(d: Path) -> tuple[dict, dict[str, list[dict]]]:
    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    out = {"agent": [], "hybrid": [], "baseline": []}
    for r in res["rows"]:
        for k in out:
            if k in r:
                out[k].append({**r[k], "latent": r["latent"], "kind": r["kind"]})
    return res, out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    diag = [r for r in rows if " " in r["diagnosed"]]
    ups = [r for r in rows if "ups_left_at_diagnosis_s" in r]
    expl = [r for r in rows if "explain_problems" in r]
    cost = [r["cost_usd"] for r in rows]
    unc = [r.get("uncached_cost_usd", 0.0 if r["cost_usd"] == 0 else None) for r in rows]
    return {
        "n": n, "correct": sum(r["correct"] for r in rows), "justified": sum(bool(r.get("justified")) and not r["correct"] for r in rows),
        "confident_wrong": sum(r["confident_wrong"] for r in rows),
        "insufficient": sum(r["diagnosed"] == "insufficient_information" for r in rows),
        "other_outcome": n - len(diag) - sum(r["diagnosed"] == "insufficient_information" for r in rows),
        "explain_pass": (sum(not r["explain_problems"] for r in expl), len(expl)) if expl else None,
        "ups_median_s": statistics.median([r["ups_left_at_diagnosis_s"] for r in ups]) if ups else None,
        "before_ups_out": (sum(r["diagnosed_before_ups_out"] for r in ups), len(ups)) if ups else None,
        "readings": sum(r["measurements"] for r in rows), "readings_mean": _mean([r["measurements"] for r in rows]),
        "approvals": sum(r["approval_requests"] for r in rows), "strong": sum(r["strong_approval_requests"] for r in rows),
        "denied": sum(r["approvals_denied"] for r in rows),
        "cost": round(sum(cost), 4), "uncached": round(sum(u for u in unc if u is not None), 4) if all(u is not None for u in unc) else None,
        "wall_mean_s": _mean([r.get("seconds") for r in rows]),
        "correct_before_ups_out": (sum(bool(r.get("diagnosed_before_ups_out")) and bool(r["correct"]) for r in ups), len(ups))
        if ups else None,
    }


def fmt(s: dict, key: str) -> str:
    v = s[key]
    if v is None:
        return "n/a"
    if key in ("correct", "justified", "confident_wrong", "insufficient", "other_outcome"):
        return f"{v}/{s['n']}"
    if key in ("explain_pass", "before_ups_out"):
        return f"{v[0]}/{v[1]}"
    if key == "ups_median_s":
        return f"{int(v) // 60}:{int(v) % 60:02d}"
    if key in ("cost", "uncached"):
        return f"${v:.3f}"
    if key == "readings_mean":
        return f"{v:.1f}"
    if key == "wall_mean_s":
        return f"{v:.0f} s"
    return str(v)


ROWS = [("Part-level correct", "correct"), ("Justified (a twin no reading separates)", "justified"),
        ("Confidently wrong", "confident_wrong"), ("Insufficient information", "insufficient"),
        ("Other outcome (turn limit, error)", "other_outcome"), ("Explanation check passed", "explain_pass"),
        ("UPS left at diagnosis, median", "ups_median_s"), ("Diagnosed before the UPS ran out", "before_ups_out"),
        ("Readings, total", "readings"), ("Readings per case", "readings_mean"), ("Approvals asked", "approvals"),
        ("Strong approvals asked", "strong"), ("Approvals denied", "denied"), ("Cost, actual", "cost"),
        ("Cost, without the cached-input discount", "uncached"), ("Wall time per case, mean", "wall_mean_s")]


def table(cols: list[tuple[str, dict]]) -> str:
    out = ["| | " + " | ".join(c for c, _ in cols) + " |", "|---|" + "---|" * len(cols)]
    for label, key in ROWS:
        out.append(f"| {label} | " + " | ".join(fmt(s, key) for _, s in cols) + " |")
    return "\n".join(out)


def case_table(rows: dict[str, list[dict]], cases: dict) -> str:
    by = {k: {r["case"]: r for r in v} for k, v in rows.items()}
    out = ["| Case | Fault | Agent | Hybrid v2 | Baseline | Explanation check |", "|---|---|---|---|---|---|"]

    def cell(r):
        if r is None:
            return "not run"
        v = "correct" if r["correct"] else "justified" if r.get("justified") else "CONFIDENTLY WRONG" if r["confident_wrong"] else "not correct"
        return f"{r['diagnosed']} ({v})"
    for cid, c in cases.items():
        h = by["hybrid"].get(cid)
        ex = "n/a" if h is None or "explain_problems" not in h else ("pass" if not h["explain_problems"] else "; ".join(h["explain_problems"]))
        faults = ", ".join(f"{f['component']}:{f.get('part', '')} {f['mode']}".replace(": ", " ") for f in c["faults"])
        out.append(f"| {cid}{' (latent)' if c.get('latent') else ''} | {faults} | {cell(by['agent'].get(cid))} | {cell(h)} | "
                   f"{cell(by['baseline'].get(cid))} | {ex} |")
    return "\n".join(out)


def main() -> None:
    import yaml

    hold_dir = ROOT / sys.argv[1]
    res, hold = holdout_rows(hold_dir)
    dev = dev_rows()
    doc = yaml.safe_load((ROOT / "scenarios" / "ats_holdout" / "holdout.yaml").read_text(encoding="utf-8"))
    hc = {c["id"]: c for c in doc["cases"]}
    S = {f"{w}_{k}": stats(v) for w, rows in (("dev", dev), ("holdout", hold)) for k, v in rows.items()}
    vis = {k: stats([r for r in v if not r["latent"]]) for k, v in hold.items()}
    lat = {k: stats([r for r in v if r["latent"]]) for k, v in hold.items()}
    OUT_JSON.write_text(json.dumps({"holdout_run": hold_dir.name, "holdout_sha256": res["holdout_sha256"],
                                    "frozen": res["frozen"], "stats": S, "holdout_visible": vis, "holdout_latent": lat,
                                    "holdout_rows": hold, "dev_rows": dev}, indent=2, default=str), encoding="utf-8")
    names = {"agent": "Agent", "hybrid": "Hybrid v2", "baseline": "Baseline"}
    print("## All cases\n")
    print(table([(f"{names[k]} {w}", S[f"{w}_{k}"]) for k in names for w in ("dev", "holdout")]))
    print("\n## Holdout, visible faults\n")
    print(table([(names[k], vis[k]) for k in names]))
    print("\n## Holdout, latent faults\n")
    print(table([(names[k], lat[k]) for k in names]))
    print("\n## Holdout per case\n")
    print(case_table(hold, hc))
    print(f"\nnot run: {res['not_run']}; smoke ok: {res['smoke_ok']}; spent ${res['spent_usd']}; wall {res['wall_s']} s")


if __name__ == "__main__":
    main()
