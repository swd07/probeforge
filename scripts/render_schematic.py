"""Render the schematic SVG from a circuit YAML.

Usage:  uv run python scripts/render_schematic.py [circuit.yaml] [out.svg]
Defaults: scenarios/circuits/star_delta_reversing.yaml -> docs/star_delta_reversing.svg
"""

import sys
from pathlib import Path

from probeforge.sim.netlist import Netlist
from probeforge.sim.schematic import render_svg

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CIRCUIT = ROOT / "scenarios" / "circuits" / "star_delta_reversing.yaml"


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CIRCUIT
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / f"{src.stem}.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_svg(Netlist.load(src)), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
