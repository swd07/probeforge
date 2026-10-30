"""The ATS netlist against ASCO drawing 978741 (stage S0): documented connections only, every part and net
with a source, the redrawn diagram with clickable terminals. The wire list below is transcribed a second time,
independently of the netlist, from 978741 sheet 6 (harness 337782-003, main TS)."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from probeforge.sim.netlist import Netlist
from probeforge.sim.schematic import render_svg

ROOT = Path(__file__).resolve().parents[1]
ATS_YAML = ROOT / "scenarios" / "circuits" / "asco_300g_978741.yaml"
NS = {"svg": "http://www.w3.org/2000/svg"}

# 978741 sheet 6, wire run listing: (wire number, end, end) as printed; wires 8 and 9 appear twice
SHEET6 = """
1 TS-8 P-1 | 2 TS-A P-2 | 3 TS-6 P-3 | 4 TS-3 P-4 | 5 TS-B P-5 | 6 TS-5 P-6 | 7 TS-4 P-7 | 8 TB/TS-14 P-8 |
9 TB/TS-15 P-9 | 10 TS-17 P-10 | 11 TS-2 P-11 | 12 TS-1 P-12 | 13 TS-16 P-13 | 14 TS-18 P-14 | 15 TS-70 P-15 |
16 TS-72 P-16 | 17 TS-4 TS-9 | 18 TS-7 TS-1 | 20 TS-3 TS-69 | 21 TS-5 TS-71 | 8 TS-14 TB/TS-14 |
9 TS-15 TB/TS-15 | 24 TB/TS-16 P-17 | 25 TS-19 P-18 | 26 TS-20 P-19 | 27 TS-21 P-20 | 28 TS-22 P-21 |
29 TS-NN P-22 | 30 TS-EN P-23 | 31 TS-LN P-24
"""
WIRES = [tuple(w.split()) for w in SHEET6.replace("\n", " ").split("|")]


@pytest.fixture(scope="module")
def ats() -> Netlist:
    return Netlist.load(ATS_YAML)


def device(end: str) -> str:
    """Drawing endpoint name -> netlist terminal: TS-8 -> TS:8, P-1 -> XP:P1, TB/TS-14 -> TBTS:14."""
    dev, _, n = end.partition("-")
    return {"TS": f"TS:{n}", "P": f"XP:P{n}", "TB/TS": f"TBTS:{n}"}[dev]


def joined(n: Netlist, a: str, b: str) -> bool:
    return n.terminal_net[a] == n.terminal_net[b]


def test_every_listed_wire_is_in_the_netlist_between_its_two_endpoints(ats):
    wires = [p for p in ats.parts.values() if p.kind == "wire"]
    assert len(wires) == len(WIRES) == 30
    for num, e1, e2 in WIRES:
        found = [w for w in wires if w.name.split("_")[0].rstrip("AB") == f"W{num}"
                 and {joined(ats, w.a, device(e1)) and joined(ats, w.b, device(e2)),
                      joined(ats, w.a, device(e2)) and joined(ats, w.b, device(e1))} & {True}]
        assert len(found) == 1, f"wire {num} {e1} - {e2}"
    # no wire connects anything the list does not
    assert {(w.name.split("_")[0]) for w in wires} == {f"W{n}" for n in "1 2 3 4 5 6 7 8A 9A 10 11 12 13 14 15 16 17 18 20 21 8B 9B 24 25 26 27 28 29 30 31".split()}


def chain(n: Netlist, start: str, steps: list[tuple[str, str]], end: str) -> None:
    """Walk a documented series path: each step is (part id, terminal it is entered by)."""
    node = n.terminal_net[start]
    for pid, entry in steps:
        p = n.parts[pid]
        assert n.terminal_net[entry] == node, f"{pid} is not entered from net {node}"
        node = n.terminal_net[p.b if entry == p.a else p.a]
    assert node == n.terminal_net[end], f"path ends at {node}, not at {end}"


def test_ts_operator_circuit_matches_sheet3(ats):
    # transfer to Normal: NA - TS 7-6 - P3/J3 - SE (NO) - J2/P2 - solenoid A-B - P5/J5 - SE (NO) - J15/P15 - TS 70-69 - NC
    chain(ats, "TS:1", [("H1:W18_TS7-W18_TS1", "H1:W18_TS1"), ("TS:6-7", "TS:7"), ("H1:W3_TS6-W3_P3", "H1:W3_TS6"),
                        ("XP:P3-J3", "XP:P3"), ("SE:J3-J2", "SE:J3"), ("XP:P2-J2", "XP:J2"), ("H1:W2_TSA-W2_P2", "H1:W2_P2"),
                        ("TS:A-B", "TS:A"), ("H1:W5_TSB-W5_P5", "H1:W5_TSB"), ("XP:P5-J5", "XP:P5"), ("SE:J5-J15", "SE:J5"),
                        ("XP:P15-J15", "XP:J15"), ("H1:W15_TS70-W15_P15", "H1:W15_P15"), ("TS:69-70", "TS:70"),
                        ("H1:W20_TS3-W20_TS69", "H1:W20_TS69")], "TS:3")
    # transfer to Emergency: EA - TS 9-8 - P1/J1 - ER (NO) - SE (NC) - J2 ... J5 - SE (NC) - ER (NO) - J16/P16 - TS 72-71 - EC
    chain(ats, "TS:4", [("H1:W17_TS4-W17_TS9", "H1:W17_TS4"), ("TS:8-9", "TS:9"), ("H1:W1_TS8-W1_P1", "H1:W1_TS8"),
                        ("XP:P1-J1", "XP:P1"), ("ER:J1-X1", "ER:J1"), ("SE:X1-J2", "SE:X1"), ("XP:P2-J2", "XP:J2"),
                        ("H1:W2_TSA-W2_P2", "H1:W2_P2")], "TS:A")
    chain(ats, "TS:B", [("H1:W5_TSB-W5_P5", "H1:W5_TSB"), ("XP:P5-J5", "XP:P5"), ("SE:J5-X2", "SE:J5"), ("ER:X2-J16", "ER:X2"),
                        ("XP:P16-J16", "XP:J16"), ("H1:W16_TS72-W16_P16", "H1:W16_P16"), ("TS:71-72", "TS:72"),
                        ("H1:W21_TS5-W21_TS71", "H1:W21_TS71")], "TS:5")
    kinds = {p.id: p.kind for p in ats.parts.values()}
    # control contacts table: 6-7 and 69-70 closed on Emergency, 8-9 and 71-72 closed on Normal
    assert (kinds["TS:6-7"], kinds["TS:69-70"], kinds["TS:8-9"], kinds["TS:71-72"]) == ("cutoff_e", "cutoff_e", "cutoff_n", "cutoff_n")
    assert (kinds["SE:J3-J2"], kinds["SE:X1-J2"], kinds["ER:J1-X1"]) == ("contact_no", "contact_nc", "contact_no")
    assert kinds["TS:A-B"] == "solenoid"


def test_main_poles_and_52u_match_sheet3_and_the_outline(ats):
    kinds = {p.id: p.kind for p in ats.parts.values()}
    for pole in ("TS:1-20", "TS:2-21", "TS:3-22", "TS:NN-LN"):
        assert kinds[pole] == "main_n"
    for pole in ("TS:4-20", "TS:19-21", "TS:5-22", "TS:EN-LN"):
        assert kinds[pole] == "main_e"
    assert [ats.terminal_net[t] for t in ("TS:1", "TS:2", "TS:3", "TS:4", "TS:19", "TS:5", "TS:20", "TS:21", "TS:22")] == \
        ["NA", "NB", "NC", "EA", "EB", "EC", "LA", "LB", "LC"]
    assert ats.power_switch == "52U" and [p.name for p in ats.components["52U"].parts] == ["1-2", "3-4", "5-6"]
    assert [ats.terminal_net[t] for t in ("52U:2", "52U:4", "52U:6")] == ["NA", "NB", "NC"]
    assert ats.phases == {"UA": 0.0, "UB": -120.0, "UC": 120.0} and ats.neutral == "NN"
    assert ats.alternate["phases"] == {"EA": 0, "EB": -120, "EC": 120} and ats.alternate["neutral"] == "EN"


@pytest.mark.parametrize("source,pin,wire", [
    ("TS:1", 12, "H1:W12_TS1-W12_P12"), ("TS:2", 11, "H1:W11_TS2-W11_P11"), ("TS:3", 4, "H1:W4_TS3-W4_P4"),
    ("TS:4", 7, "H1:W7_TS4-W7_P7"), ("TS:19", 18, "H1:W25_TS19-W25_P18"), ("TS:5", 6, "H1:W6_TS5-W6_P6"),
    ("TS:20", 19, "H1:W26_TS20-W26_P19"), ("TS:21", 20, "H1:W27_TS21-W27_P20"), ("TS:22", 21, "H1:W28_TS22-W28_P21"),
    ("TS:NN", 22, "H1:W29_TSNN-W29_P22"), ("TS:EN", 23, "H1:W30_TSEN-W30_P23"), ("TS:LN", 24, "H1:W31_TSLN-W31_P24"),
    ("TS:17", 10, "H1:W10_TS17-W10_P10"), ("TS:16", 13, "H1:W13_TS16-W13_P13"), ("TS:18", 14, "H1:W14_TS18-W14_P14"),
])
def test_sensing_and_position_inputs_match_sheet4(ats, source, pin, wire):
    w = ats.parts[wire]
    chain(ats, source, [(wire, w.a), (f"XP:P{pin}-J{pin}", f"XP:P{pin}")], f"CP:J{pin}")


def test_position_contacts_and_engine_start_match_sheets_4_and_2(ats):
    assert ats.parts["TS:17-16"].kind == "aux_e" and ats.parts["TS:17-18"].kind == "aux_n"  # 14B NO, 14A NC, common 17
    # engine starting signals: NR NC J8-J9 to TB/TS 14-15 (Feature 7 closes to start), NR NO J8-J17 to TB/TS-16
    chain(ats, "TBTS:14", [("H1:W8A_TB14-W8A_P8", "H1:W8A_TB14"), ("XP:P8-J8", "XP:P8"), ("NR:J8-J9", "NR:J8"),
                           ("XP:P9-J9", "XP:J9"), ("H1:W9A_TB15-W9A_P9", "H1:W9A_P9")], "TBTS:15")
    chain(ats, "TBTS:14", [("H1:W8A_TB14-W8A_P8", "H1:W8A_TB14"), ("XP:P8-J8", "XP:P8"), ("NR:J8-J17", "NR:J8"),
                           ("XP:P17-J17", "XP:J17"), ("H1:W24_TB16-W24_P17", "H1:W24_P17")], "TBTS:16")
    assert ats.parts["NR:J8-J9"].kind == "contact_nc" and ats.parts["NR:J8-J17"].kind == "contact_no"
    # TS aux 14B across TB/TS 14-15, in parallel with NR (NC)
    chain(ats, "TBTS:14", [("H1:W8B_TS14-W8B_TB14", "H1:W8B_TB14"), ("TS:14-15", "TS:14"),
                           ("H1:W9B_TS15-W9B_TB15", "H1:W9B_TS15")], "TBTS:15")
    assert ats.alternate["start_contact"] == ["TB14", "TB15"]


def test_every_part_and_net_has_a_source_and_assumptions_are_listed():
    data = yaml.safe_load(ATS_YAML.read_text(encoding="utf-8"))
    n = Netlist.from_dict(data)
    prov = data["provenance"]
    assert {f"part {p}" for p in n.parts} <= set(prov), sorted({f"part {p}" for p in n.parts} - set(prov))
    assert {f"net {k}" for k in n.nets} <= set(prov)
    assert all(str(v).strip() for v in prov.values())
    assert any("TS:A-B resistance" in a for a in data["assumptions"])  # the one undocumented value in the netlist
    assert "assumed" in prov["part TS:A-B"]


def test_redrawn_diagram_has_clickable_terminals_and_states_its_source(ats):
    svg = render_svg(ats)
    root = ET.fromstring(svg)
    terminals = {c.get("data-terminal") for c in root.iterfind(".//svg:circle[@data-terminal]", NS)}
    nets = {p.get("data-net") for p in root.iterfind(".//svg:path[@data-net]", NS)}
    parts = {g.get("data-part") for g in root.iterfind(".//svg:g[@data-part]", NS)}
    assert terminals == set(ats.terminal_net) and parts == set(ats.parts)
    # every net with more than one terminal is drawn (single-terminal nets are tagged)
    assert {k for k, v in ats.nets.items() if len(v) > 1} <= nets
    assert "Redrawn from ASCO Series 300 Group G wiring diagram 978741, Schneider Electric" in svg
    assert "Not the official drawing" in svg
    committed = (ROOT / "docs" / "asco_300g_978741.svg").read_text(encoding="utf-8")
    assert committed == svg, "run: uv run python scripts/render_schematic.py scenarios/circuits/asco_300g_978741.yaml docs/asco_300g_978741.svg"
