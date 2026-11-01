"""Validate the committed ATS results offline, from a clean checkout (no model calls, no local runs/ folder needed).

  python -m uv run python scripts/verify_results.py

Checks:
1. scenarios/ats_holdout/holdout.yaml matches holdout.sha256, and the holdout run's results.json names that hash and the
   same 13 fingerprints as the list.
2. Every holdout row in results.json agrees with its per-case traces (agent, Hybrid v2, baseline): same diagnosis,
   same number of readings.
3. The dev agent rows equal the committed dev run; the dev Hybrid v2 diagnoses equal the committed D42 run.
4. Every metric is recomputed from those rows and compared with docs/results/ats_results.json and with the numbers in
   the published tables: the main table of docs/results/ats_results.md and the results table of README.md.
Exit code 1 on any mismatch, with the list of mismatches.
"""

import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ats_results import DEV_AGENT, DEV_HYBRID, stats  # noqa: E402

HOLDOUT = ROOT / "scenarios" / "ats_holdout"
RUN = ROOT / "results" / "runs" / "20261031_123544_ats_holdout"
PUBLISHED = ROOT / "docs" / "results" / "ats_results.json"
RESULTS_MD = ROOT / "docs" / "results" / "ats_results.md"
README = ROOT / "README.md"
RUNNERS = ("agent", "hybrid", "baseline")
problems: list[str] = []


def check(ok: bool, what: str) -> None:
    if not ok:
        problems.append(what)


def said(d: dict | None, outcome: str) -> str:
    d = d or {}
    return (f"{d.get('component', '')}:{d.get('part') or ''} {d.get('failure_mode', '')}".replace(": ", " ")
            if outcome == "diagnosed" else outcome)


def measurements(log: list[dict]) -> int:
    n = 0
    for e in log:
        if not e.get("executed"):
            continue
        r = e.get("result", {})
        n += ("volts" in r or "ohms" in r) + len(r.get("readings_at_other_position") or []) + \
            len(r.get("readings_during_command") or []) + (len(r.get("readings") or []) if e["tool"] == "manual_operation_check" else 0)
    return n


def holdout() -> dict[str, list[dict]]:
    data = (HOLDOUT / "holdout.yaml").read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    check((HOLDOUT / "holdout.sha256").read_text(encoding="utf-8").split()[0] == sha, "holdout.yaml does not match holdout.sha256")
    doc = yaml.safe_load(data.decode("utf-8"))
    res = json.loads((RUN / "results.json").read_text(encoding="utf-8"))
    check(res["holdout_sha256"] == sha, "results.json names another holdout list")
    check(res["frozen"] == doc["frozen"] and len(doc["frozen"]) == 13, "results.json fingerprints differ from the list's")
    check([r["case"] for r in res["rows"]] == [c["id"] for c in doc["cases"]], "holdout cases differ from the list")
    out = {k: [] for k in RUNNERS}
    for r in res["rows"]:
        for k in RUNNERS:
            row = r[k]
            tr = json.loads((RUN / k / f"{r['case']}.json").read_text(encoding="utf-8"))
            log = tr.get("log") or tr.get("tool_log") or []
            check(said(tr["diagnosis"], tr["outcome"]) == row["diagnosed"], f"{k}/{r['case']}: trace diagnosis differs")
            check(measurements(log) == row["measurements"], f"{k}/{r['case']}: trace readings {measurements(log)} != {row['measurements']}")
            out[k].append({**row, "latent": r["latent"], "kind": r["kind"]})
    return out


def dev(published: dict) -> dict[str, list[dict]]:
    rows = published["dev_rows"]
    agent = json.loads((DEV_AGENT / "results.json").read_text(encoding="utf-8"))
    check(agent == rows["agent"], "dev agent rows differ from the committed dev run")
    paid = {r["case"]: r for r in json.loads((DEV_HYBRID / "results.json").read_text(encoding="utf-8"))["rows"]}
    for h in rows["hybrid"]:
        p = paid[h["case"]]
        check(said(p["diagnosis"], p["diagnosis"].get("outcome", "")) == h["diagnosed"], f"dev hybrid {h['case']}: diagnosis differs")
        check(p["problems"] == h["explain_problems"], f"dev hybrid {h['case']}: explanation check differs")
        h["explain_template"] = bool((p.get("record") or {}).get("template"))
    return rows


def numbers(cell: str) -> list[float]:
    """The numbers in a table cell; m:ss counts as seconds."""
    cell = re.sub(r"(\d+):(\d\d)", lambda m: str(int(m.group(1)) * 60 + int(m.group(2))), cell)
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", cell)]


def expected(label: str, s: dict, templates: int | None, latent: list[int] | None = None) -> list[float] | None:
    """The numbers a table row should show for one column, or None for n/a."""
    n = s["n"]
    pair = lambda k: None if s[k] is None else ([s[k], n] if isinstance(s[k], int) else list(s[k]))  # noqa: E731
    table = {
        "Cases": [n], "Part-level correct": pair("correct"), "Confidently wrong": pair("confident_wrong"),
        "Insufficient information": pair("insufficient"), "Approvals asked": [s["approvals"]],
        "Any diagnosis before the UPS ran out": pair("before_ups_out"),
        "Correct diagnosis before the UPS ran out": pair("correct_before_ups_out"),
        "Readings, total (per case)": [s["readings"], round(s["readings_mean"], 1)],
        "Readings per case": [round(s["readings_mean"], 1)],
        "Cost, actual": [round(s["cost"], 3)], "Cost, without the cached-input discount": None if s["uncached"] is None else [round(s["uncached"], 3)],
        "Cost per case (actual)": [round(s["cost"] / n, 3)],
        "UPS left at diagnosis, median": None if s["ups_median_s"] is None else [int(s["ups_median_s"])],
        "Wall time per case, mean": None if s["wall_mean_s"] is None else [round(s["wall_mean_s"])],
    }
    if label.startswith("Justified"):
        return pair("justified")
    if label.startswith("Strong approvals asked"):
        return [s["strong"]]
    if label.startswith("Explanation check passed"):
        e = s["explain_pass"]
        return None if e is None else [e[0], e[1], e[1] - templates, templates]
    if label.startswith("Latent faults"):
        return latent  # correct latent cases of all latent cases; None when the column has none
    return table.get(label, "unknown")


def compare_table(path: Path, heading: str, cols: list[tuple[str, dict, int | None, list | None]]) -> int:
    text = path.read_text(encoding="utf-8")
    i = text.index(heading)
    lines = [ln for ln in text[i:].splitlines()[1:] if ln.startswith("|")]
    rows = 0
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        label, values = cells[0], cells[1:]
        if len(values) != len(cols):
            break
        for (name, s, tmpl, lat), cell in zip(cols, values):
            want = expected(label, s, tmpl, lat)
            if want == "unknown":
                problems.append(f"{path.name}: no rule for the row {label!r}")
                break
            if cell == "free":
                cell = "0"
            if not cell:
                cell = "n/a"  # an empty cell: nothing to show in that column
            got = numbers(cell) if cell != "n/a" else None
            if want is None or got is None:
                check(want is None and got is None, f"{path.name}: {label} / {name}: {cell!r}, expected {want}")
            else:
                ok = len(got) == len(want) and all(abs(g - w) <= (0.0015 if isinstance(w, float) else 0.5) for g, w in zip(got, want))
                check(ok, f"{path.name}: {label} / {name}: {cell!r}, expected {want}")
        rows += 1
    return rows


def main() -> None:
    published = json.loads(PUBLISHED.read_text(encoding="utf-8"))
    hold = holdout()
    devr = dev(published)
    S = {f"holdout_{k}": stats(v) for k, v in hold.items()} | {f"dev_{k}": stats(v) for k, v in devr.items()}
    for key, s in S.items():
        old = published["stats"][key]
        for k in old:
            a, b = old[k], s[k]
            same = a == b or (isinstance(a, list) and list(a) == list(b)) or (isinstance(a, float) and abs(a - b) < 1e-6)
            check(same, f"ats_results.json stats {key}.{k}: published {a}, recomputed {b}")
    tmpl = lambda rows: sum(bool(r.get("explain_template")) for r in rows)  # noqa: E731

    def lat(rows):
        ls = [r for r in rows if r.get("latent")]
        return [sum(bool(r["correct"]) for r in ls), len(ls)] if ls else None

    cols = [("Agent dev", S["dev_agent"], None, lat(devr["agent"])), ("Agent holdout", S["holdout_agent"], None, lat(hold["agent"])),
            ("Hybrid v2 dev", S["dev_hybrid"], tmpl(devr["hybrid"]), lat(devr["hybrid"])),
            ("Hybrid v2 holdout", S["holdout_hybrid"], tmpl(hold["hybrid"]), lat(hold["hybrid"])),
            ("Baseline dev", S["dev_baseline"], None, lat(devr["baseline"])),
            ("Baseline holdout", S["holdout_baseline"], None, lat(hold["baseline"]))]
    n1 = compare_table(RESULTS_MD, "## Results, dev and holdout side by side", cols)
    readme_cols = [cols[0], cols[1], cols[2], cols[3], cols[5]]
    n2 = compare_table(README, "## Results", readme_cols)
    print(f"holdout: list hash, fingerprints, 28 cases x 3 runners checked against their traces")
    print(f"published: ats_results.json stats, {n1} rows of the results doc table, {n2} rows of the README table")
    if problems:
        print(f"{len(problems)} MISMATCHES:")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print("all committed results verified")


if __name__ == "__main__":
    main()
