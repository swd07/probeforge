import xml.etree.ElementTree as ET

from probeforge.sim.schematic import render_svg
from tests.conftest import ROOT

NS = {"svg": "http://www.w3.org/2000/svg"}


def test_svg_is_valid_xml_and_covers_netlist(netlist):
    root = ET.fromstring(render_svg(netlist))
    parts = {g.get("data-part") for g in root.iterfind(".//svg:g[@data-part]", NS)}
    terminals = [c.get("data-terminal") for c in root.iterfind(".//svg:circle[@data-terminal]", NS)]
    nets = {p.get("data-net") for p in root.iterfind(".//svg:path[@data-net]", NS)}
    assert parts == set(netlist.parts)
    assert sorted(terminals) == sorted(netlist.terminal_net)
    assert nets == set(netlist.nets)


def test_committed_svg_matches_yaml(netlist):
    committed = (ROOT / "docs" / "star_delta_reversing.svg").read_text(encoding="utf-8")
    assert committed == render_svg(netlist), "run: uv run python scripts/render_schematic.py"

