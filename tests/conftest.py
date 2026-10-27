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
