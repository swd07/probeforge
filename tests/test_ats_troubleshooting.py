"""The troubleshooting sheet (docs/ATS_TROUBLESHOOTING.*) is generated from the simulator and kept up to date: the
committed JSON equals a fresh generation, every dev case of families A and B is among the causes of its sheet, and the
checks follow the safe order (live readings before isolation, resistances only after it)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ats_troubleshooting as gen  # noqa: E402


def test_sheet_is_current_safe_ordered_and_covers_the_dev_cases():
    cases = gen.load_cases()
    sheets = [s for f in gen.FAMILIES for s in gen.family_sheets(f, cases)]
    committed = json.loads((ROOT / "docs" / "ATS_TROUBLESHOOTING.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps({"label": gen.LABEL, "sheets": sheets}))
    assert "not reviewed by an engineer" in committed["label"]
    md = (ROOT / "docs" / "ATS_TROUBLESHOOTING.md").read_text(encoding="utf-8")
    assert gen.LABEL in md
    for s in sheets:
        assert s["dev_cases_covered"] == s["dev_cases"]
        tools = [c["tool"] for c in s["checks"]]
        iso = tools.index("isolate_sources") if "isolate_sources" in tools else len(tools)
        assert all(t in ("measure_voltage", "read_position_indicator") for t in tools[:iso])
        assert all(t in ("measure_resistance", "manual_operation_check") for t in tools[iso + 1:])
        for c in s["checks"]:
            if c["expected"]:
                assert set(c["expected"]) == set(s["causes"])
