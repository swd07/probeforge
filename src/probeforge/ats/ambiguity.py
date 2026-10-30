"""Which ATS faults no measurement on the bench can tell apart (observational twins).

The signature of a fault is everything the bench lets a technician observe after the normal source is lost: the
controller lights, display, alarms and event log, the generator, the load and the UPS at several moments; the voltage
of every accessible net to neutral and across every accessible part in the state reached 60 s after the outage (a
command that is still active, such as ER after a Transfer Failure, is still active then); and the resistance of every
accessible part with both sources isolated, before and after operating the switch manually to the other position
(an assumed maintenance check: a jammed mechanism does not move, a cut-off contact that does not open still reads
closed). Nets inside the controller (between the SE and ER contacts) cannot be probed and are left out.
"""

from probeforge.ats.bench import INTERNAL_NETS, AtsBench
from probeforge.faults.model import Fault

SAMPLE_TIMES = (2.0, 5.0, 15.0, 30.0, 60.0)


def _panel(b: AtsBench) -> tuple:
    i = b.indicators()
    return (tuple(sorted(i["lights"].items())), i["display"], tuple(i["alarms"]),
            tuple(i["metering"]["Normal"]), tuple(i["metering"]["Emergency"]),
            tuple((e["event"], e["cause"]) for e in i["events"]), i["generator"], i["load_powered"], i["ups"]["draining"])


def signature(faults: list[Fault]) -> tuple:
    b = AtsBench(faults=faults)
    b.lose_utility()
    panel = []
    for t in SAMPLE_TIMES:
        b.step(t - b.t)
        panel.append(_panel(b))
    n = b.n
    nets = [k for k in n.nets if k not in INTERNAL_NETS]
    parts = [p for p in n.parts.values() if p.a != p.b
             and n.terminal_net[p.a] not in INTERNAL_NETS and n.terminal_net[p.b] not in INTERNAL_NETS]
    volts = tuple(b.voltage(k, "NN") for k in nets) + tuple(b.voltage(p.a, p.b) for p in parts)
    iso = b.clone()
    iso.isolate()
    ohms = tuple(iso.resistance(p.a, p.b) for p in parts)
    moved = iso.manual_operate()
    ohms_far = tuple(iso.resistance(p.a, p.b) for p in parts)
    return tuple(panel), volts, ohms, moved, ohms_far


def twins(cases: dict[str, list[Fault]]) -> list[list[str]]:
    """Groups of case ids whose signatures are identical (groups of one left out)."""
    groups: dict[tuple, list[str]] = {}
    for cid, faults in cases.items():
        groups.setdefault(signature(faults), []).append(cid)
    return [sorted(g) for g in groups.values() if len(g) > 1]
