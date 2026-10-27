"""Scenario files and the random fault generator."""

import random
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from probeforge.faults.model import COMPONENT_MODES, PART_MODES, Fault
from probeforge.sim.circuit import Circuit
from probeforge.sim.netlist import Netlist

SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "scenarios"


@dataclass
class Scenario:
    id: str
    title: str
    circuit: Path  # path to the circuit YAML
    fault: Fault
    symptom: str
    engineer_trace: list = field(default_factory=list)


def load_scenario(path: str | Path) -> Scenario:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Scenario(
        id=str(data["id"]),
        title=str(data["title"]),
        circuit=(path.parent / data["circuit"]).resolve(),
        fault=Fault.from_dict(data["fault"]),
        symptom=str(data["symptom"]),
        engineer_trace=list(data.get("engineer_trace") or []),
    )


def load_scenarios(directory: str | Path = SCENARIOS_DIR) -> list[Scenario]:
    return [load_scenario(p) for p in sorted(Path(directory).glob("s*.yaml"))]


def all_faults(netlist: Netlist) -> list[Fault]:
    """Every single fault the netlist can have: each part in each of its failure modes."""
    faults = []
    for comp in netlist.components.values():
        for mode in COMPONENT_MODES.get(comp.type, ()):
            faults.append(Fault(comp.id, mode))
        for part in comp.parts:
            for mode in PART_MODES[part.kind]:
                faults.append(Fault(comp.id, mode, part.name))
    return faults


def operator_observation(circuit: Circuit) -> list[dict]:
    """What an operator sees running the machine: power on, forward, wait, stop, reverse, wait, stop."""
    obs = []
    circuit.set_power(True)
    obs.append(circuit.indicators())
    for start in ("Start Fwd", "Start Rev"):
        circuit.press(start)
        obs.append(circuit.indicators())
        circuit.step(10)
        obs.append(circuit.indicators())
        circuit.press("Stop")
        obs.append(circuit.indicators())
    return obs


def has_visible_symptom(netlist: Netlist, fault: Fault) -> bool:
    """True if the fault changes what the operator sees. Latent faults (for example
    a welded interlock contact) only show up with measurements or a second fault."""
    faulty = Circuit(netlist)
    faulty.apply_fault(fault)
    return operator_observation(faulty) != operator_observation(Circuit(netlist))


def make_holdout(
    netlist: Netlist, seed: int = 2026, n_visible: int = 30, n_latent: int = 10, exclude: list[Fault] = ()
) -> tuple[list[Fault], list[Fault]]:
    """Fixed random holdout set: visible faults and latent faults, none of them in `exclude`."""
    rng = random.Random(seed)
    pool = [f for f in all_faults(netlist) if f not in set(exclude)]
    visible = [f for f in pool if has_visible_symptom(netlist, f)]
    latent = [f for f in pool if f not in set(visible)]
    return rng.sample(visible, min(n_visible, len(visible))), rng.sample(latent, min(n_latent, len(latent)))


def random_fault(
    netlist: Netlist, rng: random.Random | int | None = None, visible_only: bool = False
) -> Fault:
    """Pick one fault uniformly from all_faults. Pass a seed or Random for repeatable picks."""
    if not isinstance(rng, random.Random):
        rng = random.Random(rng)
    candidates = all_faults(netlist)
    if visible_only:
        candidates = [f for f in candidates if has_visible_symptom(netlist, f)]
    return rng.choice(candidates)
