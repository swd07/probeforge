from pathlib import Path

import pytest

from probeforge.sim import Circuit, Netlist

ROOT = Path(__file__).resolve().parents[1]
CIRCUIT_YAML = ROOT / "scenarios" / "circuits" / "star_delta_reversing.yaml"


@pytest.fixture(scope="session")
def netlist() -> Netlist:
    return Netlist.load(CIRCUIT_YAML)


@pytest.fixture
def circuit(netlist) -> Circuit:
    return Circuit(netlist)


@pytest.fixture
def powered(circuit) -> Circuit:
    circuit.set_power(True)
    return circuit


@pytest.fixture(autouse=True)
def _ui_runs_file(tmp_path, monkeypatch):
    """Server tests write their UI run list to a temporary file, never to runs/ui_runs.jsonl."""
    monkeypatch.setenv("PROBEFORGE_UI_RUNS", str(tmp_path / "ui_runs.jsonl"))
