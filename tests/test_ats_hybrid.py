"""Hybrid v2 on the ATS bench (no API calls): the compact transcription builder, the info-gain planner (also the ceiling
baseline on the true netlist) and the pipeline with a scripted fake model."""

from pathlib import Path

import yaml

from probeforge.ats import AtsBench
from probeforge.ats.hybrid.read import build, to_netlist

ROOT = Path(__file__).resolve().parents[1]
TRUE = AtsBench().n


def perfect_transcription() -> dict:
    """What a perfect read of the drawing sheets gives, in the compact format (derived from the true netlist)."""
    comps = yaml.safe_load((ROOT / "scenarios" / "circuits" / "asco_300g_978741.yaml").read_text(encoding="utf-8"))["components"]
    ts = comps["TS"]
    wires = []
    for name in comps["H1"]["wires"]:
        a, b = name.split("-", 1)
        num = a.split("_")[0][1:].rstrip("AB")

        def end(lbl: str) -> str:
            lbl = lbl.split("_", 1)[1]
            return f"TB/TS-{lbl[2:]}" if lbl.startswith("TB") else f"TS-{lbl[2:]}" if lbl.startswith("TS") else f"P-{lbl[1:]}"

        wires.append([num, end(a), end(b)])
    return {
        "title": "test", "normal_source": {"A": "52U:1", "B": "52U:3", "C": "52U:5"},
        "emergency_source": {"A": "TS:4", "B": "TS:19", "C": "TS:5"},
        "neutrals": {"normal": "TS:NN", "emergency": "TS:EN", "load": "TS:LN"},
        "load": {"A": "TS:20", "B": "TS:21", "C": "TS:22"},
        "breaker": {"id": "52U", "label": "52U Normal breaker", "poles": ["1-2", "3-4", "5-6"]},
        "transfer_switch": {"main_normal": ts["main_normal"], "main_emergency": ts["main_emergency"],
                            "control_closed_normal": ts["cutoff_normal"], "control_closed_emergency": ts["cutoff_emergency"],
                            "aux_closed_normal": ts["aux_normal"], "aux_closed_emergency": ts["aux_emergency"],
                            "solenoid": ts["solenoid"][0]},
        "relays": {r: {"no": comps[r].get("no_contacts", []), "nc": comps[r].get("nc_contacts", [])} for r in ("SE", "ER", "NR")},
        "controller_inputs": comps["CP"]["inputs"],
        "terminal_block": {"id": "TBTS", "label": "TB/TS", "points": [14, 15, 16]},
        "wires": wires,
        "joints": [["52U:2", "TS:1"], ["52U:4", "TS:2"], ["52U:6", "TS:3"]],
        "uncertain": [],
    }


def test_builder_reproduces_the_true_netlist_from_a_perfect_read():
    data = build(perfect_transcription())
    n = to_netlist(data)
    assert {frozenset(v) for v in n.nets.values()} == {frozenset(v) for v in TRUE.nets.values()}
    assert set(n.parts) == set(TRUE.parts)
    assert {p.id: p.kind for p in n.parts.values()} == {p.id: p.kind for p in TRUE.parts.values()}
    # the bench runs on the built netlist exactly as on the true one
    a, b = AtsBench(netlist=n), AtsBench()
    for x in (a, b):
        x.lose_utility()
        x.step(30)
    assert a.indicators()["events"] == b.indicators()["events"] and a.position == b.position == "E"


# ---------------------------------------------------------------- planner and pipeline (no API calls)

import copy  # noqa: E402

from probeforge.ats.hybrid import pipeline  # noqa: E402
from probeforge.ats.infogain import AtsInfoGain, fault_model  # noqa: E402
from probeforge.eval.scoring import grade  # noqa: E402
from probeforge.faults.model import Fault  # noqa: E402

CASES = {d["id"]: d for d in (yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "scenarios" / "ats").glob("*.yaml")))}


def bench_for(cid: str) -> AtsBench:
    c = CASES[cid]
    b = AtsBench(faults=[Fault(f["component"], f["mode"], f.get("part")) for f in (c.get("faults") or [c["fault"]])])
    b.lose_utility()
    b.step(60)
    return b


def test_documented_fault_free_sequence_checks_a_model():
    assert pipeline.healthy_sequence(TRUE) == (True, pipeline.HEALTHY_EVENTS)
    bad = perfect_transcription()
    bad["transfer_switch"]["aux_closed_normal"] = ["16-18"]  # the common terminal misread (a real read error)
    ok, events = pipeline.healthy_sequence(to_netlist(build(bad)))
    assert not ok and "Position Error" in events


def test_fault_model_includes_the_documented_compound_fault():
    fm = fault_model(TRUE)
    assert () in fm and (Fault("TS", "jammed"),) in fm
    assert (Fault("TS", "stuck_closed", "8-9"), Fault("TS", "stuck_closed", "71-72"), Fault("TS", "burnt", "A-B")) in fm


def test_infogain_ceiling_baseline_on_dev_cases():
    for cid, answer in (("a4_cutoff_8_9", Fault("TS", "stuck_open", "8-9")), ("b1_wire7_open", Fault("H1", "open", "W7_TS4-W7_P7")),
                        ("a7_burnout_chain", Fault("TS", "stuck_closed", "8-9")), ("a5_jammed", Fault("TS", "jammed"))):
        p = AtsInfoGain(bench_for(cid), TRUE, model_key="true")
        d = p.run()
        assert grade(d, answer, False)["correct"], (cid, d)
        assert all(e["verdict"] != "block" for e in p.tb.log), cid  # it stays inside the policy
    # the controller-internal series contacts are observational twins: honest insufficient information
    d = AtsInfoGain(bench_for("a3_er_output"), TRUE, model_key="true").run()
    assert d["outcome"] == "insufficient_information" and "ER:J1-X1 stuck_open" in d["note"]


class FakeChat:
    """Scripted replies for the repair and explanation calls."""

    def __init__(self, replies):
        from types import SimpleNamespace

        self.replies = list(replies)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        from types import SimpleNamespace

        text = self.replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
                               usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, prompt_tokens_details=None))


def test_model_repair_accepted_only_inside_flags_and_with_the_documented_sequence():
    bad = perfect_transcription()
    bad["transfer_switch"]["aux_closed_normal"] = ["16-18"]
    bad["uncertain"] = [{"terminals": ["TS:16", "TS:17", "TS:18"], "reason": "small print"}]
    data = build(bad)
    fixed = copy.deepcopy(bad)
    fixed["transfer_switch"]["aux_closed_normal"] = ["17-18"]
    still_bad = copy.deepcopy(bad)
    still_bad["relays"]["NR"]["nc"] = ["J9-J17"]  # a correction that breaks the engine start: rejected
    reply = lambda d: "```yaml\n" + yaml.safe_dump(d, sort_keys=False) + "```\nExplanation: re-read the position contacts"  # noqa: E731
    from probeforge.hybrid.llm import Usage

    usage = Usage()
    out, raw, flags, rec = pipeline.prepare_model(FakeChat([reply(still_bad), reply(fixed)]), usage, data, bad,
                                                  data["uncertain"], [b"png"])
    assert rec["ok"] and rec["repaired"] and len(rec["attempts"]) == 2
    assert "rejected" in rec["attempts"][0] and "rejected" not in rec["attempts"][1]
    assert pipeline.healthy_sequence(to_netlist(out))[0] and usage.turns == 2


def two_error_read() -> dict:
    """The two independent read errors seen on the real drawing (S6): the NR break contact and the right-hand
    controller block, both inside regions the reads flagged."""
    bad = perfect_transcription()
    bad["relays"] = {"SE": {"no": ["J2-J3", "X2-J5"], "nc": ["X1-J2"]}, "ER": {"no": ["J1-X1", "J5-J15"], "nc": ["J16-X2"]},
                     "NR": {"no": ["J8-J17"], "nc": ["J9-J17"]}}
    return bad


def reply_for(d: dict) -> str:
    return "```yaml\n" + yaml.safe_dump(d, sort_keys=False) + "```\nExplanation: re-read the controller blocks"


def test_repair_accepts_progress_and_finds_the_next_problem():
    from probeforge.hybrid.llm import Usage

    bad = two_error_read()
    nr_fixed = copy.deepcopy(bad)
    nr_fixed["relays"]["NR"]["nc"] = ["J8-J9"]
    both = copy.deepcopy(nr_fixed)
    both["relays"]["SE"] = {"no": ["J3-J2", "J5-J15"], "nc": ["X1-J2", "J5-X2"]}
    both["relays"]["ER"] = {"no": ["J1-X1", "X2-J16"], "nc": []}
    data = build(bad)
    assert pipeline.progress(pipeline.healthy_sequence(to_netlist(data))[1]) == 2
    asked = []

    class Capture(FakeChat):
        def create(self, **kw):
            asked.append(kw["messages"][0]["content"][0]["text"])
            return super().create(**kw)

    out, raw, flags, rec = pipeline.prepare_model(Capture([reply_for(nr_fixed), reply_for(both)]), Usage(), data, bad, [], [b"png"])
    assert rec["ok"] and rec["progress"] == [2, 3, 8] and len(rec["versions"]) == 3
    assert "accepted" in rec["attempts"][0] and "accepted" in rec["attempts"][1]
    assert "engine start contact" in asked[0] and "does not transfer" in asked[1]  # the next problem, found by the rerun


def renamed_true_netlist():
    """The true netlist with every harness and connector part renamed (ids the bench does not rely on)."""
    from probeforge.sim.netlist import Netlist

    raw = yaml.safe_load((ROOT / "scenarios" / "circuits" / "asco_300g_978741.yaml").read_text(encoding="utf-8"))
    ren = lambda s: s.replace("H1", "HZ").replace("W", "Q")  # noqa: E731
    raw["components"]["HZ"] = raw["components"].pop("H1")
    raw["components"]["HZ"]["wires"] = [ren(w) for w in raw["components"]["HZ"]["wires"]]
    raw["nets"] = {k: [ren(t) if t.startswith("H1:") else t for t in v] for k, v in raw["nets"].items()}
    for k in ("layout", "provenance"):
        raw.pop(k, None)
    return Netlist.from_dict(raw)


def test_repair_hints_never_come_from_the_true_netlist(monkeypatch):
    """The Model step's problem text and parts to check are built from the transcription and the documented sequence
    only: the same prompt with the true netlist renamed, and with any load of the true netlist made to fail."""
    from probeforge.hybrid.llm import Usage
    from probeforge.sim import netlist as netlist_mod

    bad = two_error_read()

    def prompts() -> list[str]:
        pipeline._healthy_cache.clear()
        asked = []

        class Capture(FakeChat):
            def create(self, **kw):
                asked.append(kw["messages"][0]["content"][0]["text"])
                return super().create(**kw)

        pipeline.prepare_model(Capture([reply_for(bad), reply_for(bad)]), Usage(), build(bad), bad, [], [b"png"], attempts=2)
        return asked

    normal = prompts()
    renamed = renamed_true_netlist()
    real_load = netlist_mod.Netlist.load
    monkeypatch.setattr(netlist_mod.Netlist, "load", classmethod(lambda cls, path: renamed))
    assert prompts() == normal
    monkeypatch.setattr(netlist_mod.Netlist, "load", classmethod(lambda cls, path: (_ for _ in ()).throw(AssertionError("true netlist used"))))
    assert prompts() == normal
    monkeypatch.setattr(netlist_mod.Netlist, "load", real_load)
    assert len(normal) == 2 and all("TB/TS 14" in p for p in normal)


def three_error_read() -> dict:
    """After the two forward fixes, the third read error seen on the real drawing: SE's make contact J5-J15 given to ER
    (it only matters on the retransfer to Normal)."""
    bad = perfect_transcription()
    bad["relays"] = {"SE": {"no": ["J3-J2"], "nc": ["X1-J2", "J5-X2"]}, "ER": {"no": ["J1-X1", "X2-J16", "J5-J15"]},
                     "NR": {"no": ["J8-J17"], "nc": ["J8-J9"]}}
    return bad


def test_retransfer_check_traces_the_circuit_from_the_model_and_does_not_leak(monkeypatch):
    from probeforge.sim import netlist as netlist_mod

    n = to_netlist(build(three_error_read()))
    ok, events = pipeline.healthy_sequence(n)
    assert not ok and events[-2:] == ["N Source Accepted", "Transfer Failure"]
    where, region = pipeline.where_it_breaks(n)
    assert "does not transfer back to Normal" in where and "0.0 V" in where
    # traced from the model's solenoid through the cut-offs closed on Emergency; nothing listed by hand
    assert {"TS:6", "TS:7", "TS:69", "TS:70", "TS:A", "TS:B"} <= set(region)
    renamed = renamed_true_netlist()
    monkeypatch.setattr(netlist_mod.Netlist, "load", classmethod(lambda cls, path: renamed))
    pipeline._healthy_cache.clear()
    assert pipeline.where_it_breaks(n) == (where, region)
    monkeypatch.setattr(netlist_mod.Netlist, "load", classmethod(lambda cls, path: (_ for _ in ()).throw(AssertionError("true netlist used"))))
    pipeline._healthy_cache.clear()
    assert pipeline.where_it_breaks(n) == (where, region)


def test_no_repair_attempt_when_the_check_cannot_name_a_circuit(monkeypatch):
    from probeforge.hybrid.llm import Usage

    monkeypatch.setattr(pipeline, "where_it_breaks", lambda n: ("somewhere unknown", []))
    bad = three_error_read()
    out, raw, flags, rec = pipeline.prepare_model(FakeChat([]), Usage(), build(bad), bad, [], [b"png"])  # no reply scripted
    assert not rec["ok"] and rec["attempts"] == [] and "cannot name a circuit" in rec["stopped"]


def test_hybrid_v2_is_frozen():
    """Hybrid v2 frozen on 2026-10-31 (DECISIONS.md D34): changing a fingerprinted component needs approval first."""
    from probeforge.ats.freeze import ats_frozen_hashes

    assert ats_frozen_hashes() == {'ats_hybrid_read': '08b4676a5c4b', 'ats_hybrid_pipeline': '7f2625bda2ac', 'ats_infogain': '2eff9c8764c1', 'ats_sheet_crops': '5687e25c8ce3'}
