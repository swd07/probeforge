"""Which faults no tool sequence can tell apart.

Two faults are observational twins when every observation the tools can make
is identical: the operator run, every net voltage at rest, while each button is
held and after it is released, and every part resistance with power off. For
such a pair (for example a welded start button and the welded self-hold
contact across the same two nets) insufficient_information, or naming either
twin, is a justified answer.
"""

from functools import lru_cache

from probeforge.faults.catalog import all_faults, operator_observation
from probeforge.faults.model import Fault
from probeforge.sim import Circuit, Netlist


def observation_signature(netlist: Netlist, fault: Fault | None) -> str:
    def fresh() -> Circuit:
        c = Circuit(netlist)
        if fault:
            c.apply_fault(fault)
        c.set_power(True)
        return c

    nets = list(netlist.nets)
    sig: list = [repr(operator_observation(fresh()))]
    c = fresh()
    sig.append([c.voltage(x, netlist.neutral) for x in nets])
    for button in netlist.components_of("button"):
        c = fresh()
        c.hold(button.id)
        c.step(0.5)
        sig.append((repr(c.indicators()), [c.voltage(x, netlist.neutral) for x in nets]))
        c.release(button.id)
        c.step(7)
        sig.append((repr(c.indicators()), [c.voltage(x, netlist.neutral) for x in nets]))
    c = fresh()
    c.set_power(False)
    sig.append([c.resistance(p.a, p.b) for p in netlist.parts.values()])
    return repr(sig)


@lru_cache(maxsize=4)
def _signatures(circuit_path: str) -> dict[Fault, str]:
    netlist = Netlist.load(circuit_path)
    return {f: observation_signature(netlist, f) for f in all_faults(netlist)}


def observational_twins(circuit_path: str, fault: Fault) -> list[Fault]:
    sigs = _signatures(str(circuit_path))
    return [g for g, s in sigs.items() if g != fault and s == sigs[fault]]


def justified(diagnosis: dict | None, fault: Fault, twins: list[Fault], correct: bool) -> bool:
    """Correct, or the truth has observational twins and the answer was honest or named a twin."""
    if correct:
        return True
    if not twins or not diagnosis:
        return False
    if diagnosis.get("outcome") == "insufficient_information":
        return True
    named = (str(diagnosis.get("component", "")).upper(), str(diagnosis.get("failure_mode", "")))
    return any((t.component.upper(), t.mode) == named for t in twins)
