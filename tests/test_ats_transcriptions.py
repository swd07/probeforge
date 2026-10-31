"""Saved ATS transcriptions (scenarios/transcriptions/ats/): labelled with the run they were recorded in, model outputs
only, and each reproduces the documented fault-free sequence as recorded."""

from probeforge.ats.hybrid.pipeline import healthy_sequence
from probeforge.ats.hybrid.read import to_netlist
from probeforge.ats.transcriptions import DEFAULT, available, load


def test_saved_transcriptions_are_labelled_and_pass_the_model_check():
    saved = available()
    assert DEFAULT in [t["id"] for t in saved] and len(saved) >= 2
    for meta in saved:
        t = load(meta["id"])
        assert t["run_id"].endswith("_ats_hybrid") and t["recorded"].startswith("2026-")
        assert t["healthy"]["ok"] and healthy_sequence(to_netlist(t["data"]))[0]
        assert t["repairs"] == len([a for a in t["healthy"]["attempts"] if a.get("accepted")])
        assert {q["version"] for q in t["read_quality"]} and t["disclosure"]


def test_unknown_or_path_ids_are_refused():
    for bad in ("nope", "../circuits/asco_300g_978741"):
        try:
            load(bad)
        except KeyError:
            continue
        raise AssertionError(bad)
