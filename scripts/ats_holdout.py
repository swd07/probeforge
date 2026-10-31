"""S5 holdout on the ATS bench (decision D45): the case list is made once by a fixed seed after the freeze and committed
with its hash before any run; the run is single, with batch approvals, and checks the hash, the commit and the frozen
fingerprints before it starts.

  python -m uv run python scripts/ats_holdout.py make      (free: writes scenarios/ats_holdout/holdout.yaml + .sha256)
  python -m uv run python scripts/ats_holdout.py run       (paid, cap $6: agent, Hybrid v2 and the info-gain baseline)

Pool (all from the fault catalog of the bench, never hand-picked):
- 24 single faults visible on the controller panel during the outage, sampled by the seed, excluding every fault of a
  dev case, the observational twins of the dev cases (no bench reading separates them from a dev case), and every ATS
  fault run in the UI before the list was made (the local list runs/ui_runs.jsonl, D44, plus the runs before it);
- the other side of the documented burnout chain (not a dev case);
- 3 latent faults (no symptom on the panel during the outage), sampled by the seed. Rule, fixed here before any run:
  the correct outcome is insufficient information (no fault visible); any confident diagnosis counts as confidently
  wrong, even one that names a twin.

Run: the first 5 cases are the smoke test, checked for technical failures only (an error or a crash in any runner);
with none, the other cases follow in the same run; with one, the run stops and nothing is changed or re-run. Spending
cap $6: no new case starts once the next one could pass it.
"""

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_ats import accepted_answers, case_faults, load_cases, run_case, scenario_bench  # noqa: E402
from run_ats_hybrid import row as hybrid_row  # noqa: E402

from probeforge.agent.client import MUSE_SPARK, make_client  # noqa: E402
from probeforge.agent.loop import _cost  # noqa: E402
from probeforge.ats import AtsBench  # noqa: E402
from probeforge.ats.ambiguity import signature  # noqa: E402
from probeforge.ats.faults import all_faults  # noqa: E402
from probeforge.ats.freeze import ats_frozen_hashes  # noqa: E402
from probeforge.ats.hybrid.explain import check_text, consequence_split  # noqa: E402
from probeforge.ats.hybrid.pipeline import healthy_sequence, run_ats_hybrid, warm  # noqa: E402
from probeforge.ats.hybrid.read import sheet_images, to_netlist  # noqa: E402
from probeforge.ats.infogain import AtsInfoGain, fault_model  # noqa: E402
from probeforge.ats.transcriptions import DEFAULT, load  # noqa: E402
from probeforge.eval.spend import SpendLedger, SpendLimitError  # noqa: E402
from probeforge.eval.trace import make_trace  # noqa: E402
from probeforge.faults.model import Fault  # noqa: E402
from probeforge.hybrid.llm import Usage  # noqa: E402
from probeforge.server import ui_runs  # noqa: E402
from probeforge.server.ats import catalog_signatures, visible_pool  # noqa: E402

DIR = ROOT / "scenarios" / "ats_holdout"
FILE, SHA = DIR / "holdout.yaml", DIR / "holdout.sha256"
SEED = 20261031
N_VISIBLE, N_LATENT, SMOKE, CAP_USD = 24, 3, 5, 6.0
IN_FLIGHT = 5  # parallel cases
EST_AGENT_USD = 0.17  # dev uncached mean per agent case, used for the cap check
EST_HYBRID_USD = 0.02
# UI runs on random faults before the local list existed (D44)
UI_BEFORE_LIST = [{"when": "2026-10-31T10:38", "mode": "agent", "faults": ["TS:4-20 stuck_open"]}]
UI_UNKNOWN = ("2026-10-31T11:33: one UI agent run on a random fault that was not recorded and is not remembered; it may "
              "be in this pool. Nothing was tuned on it.")
LATENT_RULE = ("Latent faults: the correct outcome is insufficient information (no fault visible); any confident "
               "diagnosis counts as confidently wrong, even one that names a twin.")


def parse_fault(s: str) -> Fault:
    target, _, mode = s.strip().rpartition(" ")
    comp, _, part = target.partition(":")
    return Fault(comp, mode, part or None)


def fdict(f: Fault) -> dict:
    return {"component": f.component, "part": f.part, "mode": f.mode} if f.part else {"component": f.component, "mode": f.mode}


def make() -> None:
    if FILE.exists():
        sys.exit(f"{FILE.relative_to(ROOT)} exists: the holdout list is made once")
    n = AtsBench().n
    cases = load_cases()
    dev = {f for c in cases.values() for f in case_faults(c) + accepted_answers(c)}
    dev_sigs = {signature(case_faults(c)) for c in cases.values()}
    twins = sorted({f for f, s in catalog_signatures().items() if s in dev_sigs and f not in dev}, key=str)
    ui = UI_BEFORE_LIST + [{"when": r["when"], "mode": r["mode"], "faults": r["faults"]} for r in ui_runs.faults_run("ats")]
    ui_faults = {parse_fault(x) for r in ui for x in r["faults"]}
    excluded = dev | set(twins) | ui_faults
    visible = set(visible_pool())
    pool_v = sorted((f for f in visible if f not in excluded), key=str)
    pool_l = sorted((f for f in all_faults(n) if f not in visible and f not in excluded), key=str)
    rng = random.Random(SEED)
    pick_v, pick_l = rng.sample(pool_v, N_VISIBLE), rng.sample(pool_l, N_LATENT)
    # the burnout chain on the side no dev case uses: both cut-offs stuck closed and the coil they burnt
    chains = [c for c in fault_model(n) if len(c) == 3 and not set(c[:2]) & dev]  # the coil is shared with a7
    if len(chains) != 1:
        sys.exit(f"expected one burnout chain outside the dev cases, found {chains}")
    chain = chains[0]
    out = []
    for f in pick_v:
        out.append({"faults": [fdict(f)], "root_cause": fdict(f), "latent": False, "kind": "visible single fault"})
    out.append({"faults": [fdict(f) for f in chain], "root_cause": fdict(chain[0]), "also_accepted": [fdict(chain[1])],
                "latent": False, "kind": "burnout chain, other side (root: either cut-off; the coil is the consequence)"})
    for f in pick_l:
        out.append({"faults": [fdict(f)], "root_cause": fdict(f), "latent": True, "kind": "latent single fault"})
    for i, c in enumerate(out, 1):
        c["id"] = f"h{i:02d}"
        c["family"] = "holdout"
    print(f"burnout chain {[str(f) for f in chain]} visible on the panel: {_visible(chain)}")
    doc = {
        "created": datetime.now().isoformat(timespec="seconds"), "seed": SEED, "frozen": ats_frozen_hashes(),
        "pool": {"catalog": len(all_faults(n)), "visible": len(visible), "visible_after_exclusions": len(pool_v),
                 "latent_after_exclusions": len(pool_l)},
        "exclusions": {"dev_faults": sorted(map(str, dev)), "dev_twins": [str(f) for f in twins],
                       "ui_runs": ui, "ui_unknown": UI_UNKNOWN},
        "rules": {"latent": LATENT_RULE, "smoke": f"the first {SMOKE} cases, technical failures only, no changes",
                  "approvals": "batch: approval tier approved, strong approval denied", "cap_usd": CAP_USD,
                  "runs": "one run, no reruns"},
        "cases": [{k: c[k] for k in ("id", "family", "kind", "latent", "faults", "root_cause", "also_accepted") if k in c}
                  for c in out],
    }
    DIR.mkdir(parents=True, exist_ok=True)
    FILE.write_text(yaml.safe_dump(doc, sort_keys=False, width=120), encoding="utf-8", newline="\n")
    sha = hashlib.sha256(FILE.read_bytes()).hexdigest()
    SHA.write_text(sha + "  holdout.yaml\n", encoding="utf-8", newline="\n")
    print(f"{len(out)} cases written; sha256 {sha}")
    for c in out:
        print(f"  {c['id']} {'latent ' if c['latent'] else ''}{', '.join(_s(x) for x in c['faults'])}")


def _visible(faults) -> bool:
    from probeforge.server.ats import _face, _outage
    return _face(_outage(list(faults))) != _face(_outage([]))


def _s(d: dict) -> str:
    return f"{d['component']}:{d['part']} {d['mode']}" if d.get("part") else f"{d['component']} {d['mode']}"


# ------------------------------------------------------------------ run

def verified() -> dict:
    data = FILE.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if SHA.read_text(encoding="utf-8").split()[0] != sha:
        sys.exit("holdout.yaml does not match holdout.sha256")
    for p in (FILE, SHA):
        rel = p.relative_to(ROOT).as_posix()
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True).returncode == 0
        clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=ROOT).returncode == 0
        if not (tracked and clean):
            sys.exit(f"{rel} must be committed unchanged before the run")
    doc = yaml.safe_load(data.decode("utf-8"))
    if doc["frozen"] != ats_frozen_hashes():
        diff = {k: (v, ats_frozen_hashes().get(k)) for k, v in doc["frozen"].items() if ats_frozen_hashes().get(k) != v}
        sys.exit(f"frozen fingerprints changed since the list was made: {diff}")
    return {**doc, "sha256": sha}


def latent_scores(r: dict, latent: bool) -> dict:
    """The fixed latent rule; visible cases keep the shared scores."""
    if not latent:
        return r
    insufficient = r["diagnosed"] == "insufficient_information"
    asserted = " " in r["diagnosed"]  # a diagnosis reads "TS 4-20 stuck_open"; other outcomes are single tokens
    return {**r, "correct": insufficient, "justified": False, "confident_wrong": asserted}


def run() -> None:
    doc = verified()
    cases = {c["id"]: c for c in doc["cases"]}
    order = list(cases)
    ledger = SpendLedger()
    try:
        ledger.check(CAP_USD, what=f"ATS S5 holdout, {len(order)} cases")
    except SpendLimitError as e:
        sys.exit(str(e))
    out = ROOT / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}_ats_holdout"
    (out / "agent").mkdir(parents=True)
    (out / "hybrid").mkdir()
    (out / "baseline").mkdir()
    client, images = make_client(), sheet_images()
    t = load(DEFAULT)
    ok, events = healthy_sequence(to_netlist(t["data"]))
    healthy = {"ok": ok, "events": events}
    warm(t["data"], t["flags"])
    true = AtsBench().n
    spent: list[float] = []
    args = SimpleNamespace(model=MUSE_SPARK, effort="low", max_turns=30, transport="chat", cap=0.0)
    print(f"holdout {doc['sha256'][:12]}, {len(order)} cases, frozen {doc['frozen']}", flush=True)

    def one(cid: str) -> dict | None:
        if sum(spent) + (EST_AGENT_USD + EST_HYBRID_USD) * IN_FLIGHT > CAP_USD:
            return None  # the cap: no new case starts once the cases in flight could pass it
        case = cases[cid]
        rec = {"case": cid, "kind": case["kind"], "latent": case["latent"], "technical": []}
        try:
            a = run_case(cid, case, args, client, out / "agent", ledger, spent)
            rec["agent"] = latent_scores(a, case["latent"])
            if a.get("error"):
                rec["technical"].append(f"agent: {a['error']}")
        except Exception as e:  # noqa: BLE001 - recorded as a technical failure
            rec["technical"].append(f"agent crashed: {type(e).__name__}: {e}")
        usage = Usage(effort="medium")
        t0 = time.perf_counter()
        try:
            r = run_ats_hybrid(scenario_bench(case), client, t["data"], t["raw"], images, usage=usage, flags=t["flags"],
                               repair=True, do_explain=True, healthy=healthy)
            co, dmg = consequence_split(r.planner, r.diagnosis)
            problems = check_text(r.explanation, r.diagnosis, r.planner.models[0], consequences=co + dmg, damaged=dmg)
            h = hybrid_row(cid, case, r.diagnosis, r.outcome, r.planner.tb, usage, r.seconds,
                           {"corrections": len([c for c in r.corrections if not c.get("rejected")]),
                            "explanation": r.explanation, "explain_problems": problems,
                            "explain_template": bool((r.explain_record or {}).get("template")),
                            "uncached_cost_usd": round(_cost(usage.model, usage.prompt_tokens, 0, usage.completion_tokens), 4)})
            rec["hybrid"] = latent_scores(h, case["latent"])
            trace = make_trace(case=cid, runner="ats_hybrid", tb=r.planner.tb, diagnosis=r.diagnosis, outcome=r.outcome,
                               seconds=r.seconds, run=usage, notes=r.planner.notes,
                               extra={"explanation": r.explanation, "explain_record": r.explain_record,
                                      "corrections": r.corrections})
            (out / "hybrid" / f"{cid}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            rec["technical"].append(f"hybrid crashed: {type(e).__name__}: {e}")
        finally:
            ledger.record(usage.cost_usd, f"{out.name}/hybrid/{cid}")
            spent.append(usage.cost_usd)
        t0 = time.perf_counter()
        try:
            p = AtsInfoGain(scenario_bench(case), true, model_key="true")
            d = p.run()
            rec["baseline"] = latent_scores(hybrid_row(cid, case, d, d["outcome"], p.tb, None, time.perf_counter() - t0, {}),
                                            case["latent"])
            trace = make_trace(case=cid, runner="ats_infogain", tb=p.tb, diagnosis=d, outcome=d["outcome"],
                               seconds=time.perf_counter() - t0, notes=p.notes)
            (out / "baseline" / f"{cid}.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            rec["technical"].append(f"baseline crashed: {type(e).__name__}: {e}")
        print(f"{cid}: agent {rec.get('agent', {}).get('diagnosed')} | hybrid {rec.get('hybrid', {}).get('diagnosed')} | "
              f"baseline {rec.get('baseline', {}).get('diagnosed')} | spent ${sum(spent):.2f}"
              + (f" | TECHNICAL {rec['technical']}" if rec["technical"] else ""), flush=True)
        return rec

    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=SMOKE) as ex:
        smoke = list(ex.map(one, order[:SMOKE]))
    bad = [r for r in smoke if r is None or r["technical"]]
    rest: list = []
    if bad:
        print(f"SMOKE TEST: technical failures, the run stops here: {[r and (r['case'], r['technical']) for r in bad]}")
    else:
        print("smoke test: no technical failures; the other cases follow", flush=True)
        with ThreadPoolExecutor(max_workers=IN_FLIGHT) as ex:
            rest = list(ex.map(one, order[SMOKE:]))
    rows = [r for r in smoke + rest if r is not None]
    not_run = [c for c, r in zip(order, smoke + rest + [None] * (len(order) - len(smoke) - len(rest))) if r is None]
    result = {"holdout_sha256": doc["sha256"], "frozen": doc["frozen"], "seed": doc["seed"], "smoke_ok": not bad,
              "not_run": not_run, "spent_usd": round(sum(spent), 4), "wall_s": round(time.perf_counter() - t_start, 1),
              "rows": rows}
    (out / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"done: {len(rows)} cases, not run {not_run}, spent ${sum(spent):.3f}; written to {out.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("make", "run"))
    a = ap.parse_args()
    make() if a.what == "make" else run()


if __name__ == "__main__":
    main()
