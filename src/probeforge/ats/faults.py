"""ATS fault catalog: every part of the ATS netlist in each of its failure modes, plus the mechanism jam.

Separate from probeforge.faults (the relay-panel catalog), which stays unchanged. Failure modes per part kind:
harness wires and plug/jack pins open (a broken wire or a loose pin, as listed on 978741 sheet 6); TS main poles,
cut-off and auxiliary contacts stuck open or stuck closed (a stuck-closed cut-off contact is one that does not open at
top dead center); controller relay contacts stuck open or stuck closed (inside the controller: not separately
accessible, so they are diagnosed as the controller output); the TS solenoid open or burnt open; a controller input
failed (reads nothing); the mechanism jammed. The 52U poles and the TB/TS points are not faulted (52U stays closed by
decision D23; a TB/TS point fault is the same as the wire on it).
"""

from probeforge.faults.model import Fault
from probeforge.sim.netlist import Netlist

PART_MODES = {
    "wire": ("open",),
    "pin": ("open",),
    "main_n": ("stuck_open", "stuck_closed"),
    "main_e": ("stuck_open", "stuck_closed"),
    "cutoff_n": ("stuck_open", "stuck_closed"),
    "cutoff_e": ("stuck_open", "stuck_closed"),
    "aux_n": ("stuck_open", "stuck_closed"),
    "aux_e": ("stuck_open", "stuck_closed"),
    "contact_no": ("stuck_open", "stuck_closed"),
    "contact_nc": ("stuck_open", "stuck_closed"),
    "solenoid": ("open", "burnt"),
    "input": ("open",),
}
COMPONENT_MODES = {"transfer_switch": ("jammed",)}


def all_faults(netlist: Netlist) -> list[Fault]:
    out = []
    for comp in netlist.components.values():
        for mode in COMPONENT_MODES.get(comp.type, ()):
            out.append(Fault(comp.id, mode))
        for part in comp.parts:
            for mode in PART_MODES.get(part.kind, ()):
                out.append(Fault(comp.id, mode, part.name))
    return out


def validate(netlist: Netlist, fault: Fault) -> None:
    comp = netlist.components.get(fault.component)
    if comp is None:
        raise ValueError(f"unknown component {fault.component}")
    if fault.part is None:
        if fault.mode not in COMPONENT_MODES.get(comp.type, ()):
            raise ValueError(f"{fault.component} cannot fail as {fault.mode!r}")
        return
    part = next((p for p in comp.parts if p.name == fault.part), None)
    if part is None or fault.mode not in PART_MODES.get(part.kind, ()):
        raise ValueError(f"{fault.component}:{fault.part} cannot fail as {fault.mode!r}")
