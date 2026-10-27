"""Relay-contactor circuit simulator.

Model:
- Closed switches (contacts, fuse and breaker poles, thermal relay heaters) are
  ideal conductors. Nets joined by them form groups (union-find).
- A group that touches a supply net is live at that phase. A group touching
  two supply nets is a short circuit: the first protection device whose
  opening clears it blows (fuse) or trips (breaker).
- A load (coil, lamp) is energized when its two terminals sit in groups live at
  different potentials. Coils move their contactor armature; the loop repeats
  until nothing changes.
- The motor is evaluated from which phases reach U1/V1/W1 and whether KM3
  (star) or KM4 (delta) connects the winding ends.
- Time advances in ticks: the on-delay timer counts while its coil is
  energized, the thermal relay heats while any motor line is overcurrent.
- Measurements use nodal analysis over the same groups, with loads as
  resistors, so a voltmeter across an open contact reads the supply voltage
  like it would on a real panel.
"""

import cmath
import math
from pathlib import Path

from probeforge.faults.model import COMPONENT_MODES, PART_MODES, Fault
from probeforge.sim.netlist import CONTACT_KINDS, LOAD_KINDS, Netlist, Part
from probeforge.sim.solver import UnionFind, node_potentials

TICK = 0.1  # seconds per simulation tick
ENERGIZE_FRACTION = 0.65  # a load needs this fraction of phase voltage to pick up
MAX_SETTLE = 50
FORWARD_SEQUENCES = {("L1", "L2", "L3"), ("L2", "L3", "L1"), ("L3", "L1", "L2")}


class CircuitError(RuntimeError):
    pass


class Circuit:
    def __init__(self, netlist: Netlist):
        self.netlist = netlist
        n = netlist
        self.time = 0.0
        self.power = False
        self.held: set[str] = set()
        self.closed = {c.id: False for c in n.components_of("contactor")}
        self.timer_on = {c.id: False for c in n.components_of("timer")}
        self.timer_elapsed = {c.id: 0.0 for c in n.components_of("timer")}
        self.thermal_heat = {c.id: 0.0 for c in n.components_of("thermal_relay")}
        self.tripped = {c.id: False for c in n.components_of("thermal_relay")}
        self.blown: set[str] = set()  # fuse poles opened by a short circuit
        self.events: list[str] = []  # protection operations, for logs and the UI

        self._faults: list[Fault] = []
        self._part_fault: dict[str, str] = {}
        self._comp_fault: dict[str, str] = {}

        self._sources = {name: n.voltage * cmath.exp(1j * math.radians(deg)) for name, deg in n.phases.items()}
        self._sources[n.neutral] = 0j
        self._coil = {
            c.id: next(p for p in c.parts if p.kind == "coil") for c in n.components.values() if c.type in ("contactor", "timer")
        }
        self._lamps = [c for c in n.components.values() if c.type == "lamp"]
        motors = n.components_of("motor")
        self._windings: list[Part] = motors[0].parts if motors else []
        self._load_parts = [p for p in n.parts.values() if p.kind in LOAD_KINDS]

        self._settle()

    @classmethod
    def load(cls, path: str | Path) -> "Circuit":
        return cls(Netlist.load(path))

    # ------------------------------------------------------------------ actions

    def apply_fault(self, fault: Fault) -> None:
        comp = self.netlist.components.get(fault.component)
        if comp is None:
            raise ValueError(f"unknown component {fault.component!r}")
        if fault.part:
            part = self.netlist.parts.get(f"{comp.id}:{fault.part}")
            if part is None:
                raise ValueError(f"{comp.id} has no part {fault.part!r}")
            if fault.mode not in PART_MODES[part.kind]:
                raise ValueError(f"{part.id} ({part.kind}) cannot fail as {fault.mode!r}")
            self._part_fault[part.id] = fault.mode
        else:
            if fault.mode not in COMPONENT_MODES.get(comp.type, ()):
                raise ValueError(f"{comp.id} ({comp.type}) cannot fail as {fault.mode!r}")
            self._comp_fault[comp.id] = fault.mode
            if fault.mode == "tripped":
                self.tripped[comp.id] = True
        self._faults.append(fault)
        self._settle()

    def set_power(self, on: bool) -> None:
        self.power = bool(on)
        self._settle()

    def hold(self, button: str) -> None:
        self.held.add(self._button(button))
        self._settle()

    def release(self, button: str) -> None:
        self.held.discard(self._button(button))
        self._settle()

    def press(self, button: str, duration: float = 0.2) -> None:
        """Momentary press: hold the button for `duration` seconds, then release."""
        self.hold(button)
        self.step(duration)
        self.release(button)

    def reset(self, component: str) -> None:
        """Manual reset of a thermal overload relay."""
        comp = self.netlist.find_component(component)
        if comp.type != "thermal_relay":
            raise ValueError(f"{comp.id} is not a thermal relay")
        self.tripped[comp.id] = False
        self.thermal_heat[comp.id] = 0.0
        self._settle()

    def step(self, dt: float) -> None:
        for _ in range(int(round(dt / TICK))):
            self._tick(TICK)

    # ------------------------------------------------------------- observation

    def indicators(self) -> dict:
        return {
            "lamps": dict(self._lamp_state),
            "motor": self._motor_state,
            "phase_currents": dict(self._currents),
        }

    def voltage(self, a: str, b: str) -> float:
        """RMS voltage a voltmeter would read between two points (terminal or net name)."""
        ra, rb = self._uf.find(self._net_of(a)), self._uf.find(self._net_of(b))
        if self._potential_cache is None:
            fixed = {root: self._sources[next(iter(s))] for root, s in self._src.items() if len(s) == 1}
            self._potential_cache = node_potentials(self._roots(), self._load_edges(), fixed)
        va, vb = self._potential_cache[ra], self._potential_cache[rb]
        if va is None or vb is None:
            return 0.0
        return round(abs(va - vb), 1)

    def resistance(self, a: str, b: str) -> float:
        """Ohmmeter reading between two points; math.inf when open.

        Treats the circuit as passive (supply not driving it), which is only
        physically meaningful with the power off. Enforcing that is the job of
        the policy layer, not the simulator.
        """
        ra, rb = self._uf.find(self._net_of(a)), self._uf.find(self._net_of(b))
        if ra == rb:
            return 0.0
        pot = node_potentials(self._roots(), self._load_edges(), {rb: 0j}, {ra: 1.0})
        v = pot[ra]
        return math.inf if v is None else round(v.real, 1)

    def net_of(self, point: str) -> str:
        """Net a probe point (terminal id or net name) belongs to."""
        return self._net_of(point)

    def conducting_parts(self) -> set[str]:
        """Switch-type parts (contacts, poles, heaters) that conduct right now."""
        return {p.id for p in self.netlist.parts.values() if p.kind not in LOAD_KINDS and self._conducts(p)}

    def energized_loads(self) -> list[str]:
        """Coils and lamps with supply voltage across them right now, in netlist order."""
        return [
            p.id
            for p in self._load_parts
            if p.kind != "winding" and self._energized(p, self._uf, self._src)
        ]

    # ---------------------------------------------------------------- internals

    def _button(self, name: str) -> str:
        comp = self.netlist.find_component(name)
        if comp.type != "button":
            raise ValueError(f"{comp.id} is not a button")
        return comp.id

    def _net_of(self, point: str) -> str:
        point = point.strip()
        if point in self.netlist.nets:
            return point
        if point in self.netlist.terminal_net:
            return self.netlist.terminal_net[point]
        raise KeyError(f"unknown point {point!r}")

    def _timer_done(self, tid: str) -> bool:
        delay = float(self.netlist.components[tid].params.get("delay", 0.0))
        return (
            self.timer_on[tid]
            and self.timer_elapsed[tid] >= delay - 1e-6
            and self._comp_fault.get(tid) != "stuck"
        )

    def _actuated(self, p: Part) -> bool:
        comp = self.netlist.components[p.component]
        if comp.type == "button":
            return comp.id in self.held
        if comp.type == "contactor":
            return self.closed[comp.id]
        if comp.type == "timer":
            return self._timer_done(comp.id) if p.kind.startswith("delayed") else self.timer_on[comp.id]
        if comp.type == "thermal_relay":
            return self.tripped[comp.id]
        raise CircuitError(f"{p.id}: contact on a {comp.type}")

    def _conducts(self, p: Part, extra_open: frozenset = frozenset()) -> bool:
        mode = self._part_fault.get(p.id)
        if p.kind in LOAD_KINDS:
            return mode == "short"
        if p.id in extra_open or mode in ("open", "stuck_open"):
            return False
        if mode == "stuck_closed":
            return True
        if p.kind == "breaker_pole":
            return self.power
        if p.kind == "fuse_pole":
            return p.id not in self.blown
        if p.kind == "heater":
            return True
        return self._actuated(p) == CONTACT_KINDS[p.kind]

    def _groups(self, extra_open: frozenset = frozenset()):
        uf = UnionFind(self.netlist.nets)
        tn = self.netlist.terminal_net
        for p in self.netlist.parts.values():
            if self._conducts(p, extra_open):
                uf.union(tn[p.a], tn[p.b])
        src: dict[str, set[str]] = {}
        for s in self._sources:
            src.setdefault(uf.find(s), set()).add(s)
        return uf, src

    def _clear_shorts(self):
        uf, src = self._groups()
        while any(len(s) > 1 for s in src.values()):
            uf, src = self._trip_protection()
        return uf, src

    def _trip_protection(self):
        for dev in self.netlist.protection:
            comp = self.netlist.components[dev]
            poles = [p.id for p in comp.parts if self._conducts(p)]
            if not poles:
                continue
            for opened in [[p] for p in poles] + [poles]:
                _, src = self._groups(frozenset(opened))
                if all(len(s) <= 1 for s in src.values()):
                    if comp.type == "breaker":
                        self.power = False
                        self.events.append(f"t={self.time:.1f}s {dev} tripped on short circuit")
                    else:
                        self.blown.update(opened)
                        self.events.append(f"t={self.time:.1f}s {', '.join(opened)} blew on short circuit")
                    return self._groups()
        raise CircuitError("short circuit not cleared by any protection device")

    def _phase(self, root, src) -> str | None:
        s = src.get(root)
        return next(iter(s)) if s and len(s) == 1 else None

    def _load_voltage(self, p: Part, uf, src) -> float:
        if self._part_fault.get(p.id) in ("open", "short"):
            return 0.0
        tn = self.netlist.terminal_net
        sa, sb = self._phase(uf.find(tn[p.a]), src), self._phase(uf.find(tn[p.b]), src)
        if sa is None or sb is None:
            return 0.0
        return abs(self._sources[sa] - self._sources[sb])

    def _energized(self, p: Part, uf, src) -> bool:
        return self._load_voltage(p, uf, src) >= ENERGIZE_FRACTION * self.netlist.voltage

    def _settle(self) -> None:
        for _ in range(MAX_SETTLE):
            uf, src = self._clear_shorts()
            coil_on = {cid: self._energized(p, uf, src) for cid, p in self._coil.items()}
            new_closed = {cid: coil_on[cid] or self._comp_fault.get(cid) == "welded" for cid in self.closed}
            for a, b in self.netlist.interlocks:
                if new_closed[a] and new_closed[b]:
                    wa, wb = self._comp_fault.get(a) == "welded", self._comp_fault.get(b) == "welded"
                    if wa and not wb:
                        new_closed[b] = False
                    elif wb and not wa:
                        new_closed[a] = False
                    elif self.closed[b] and not self.closed[a]:
                        new_closed[a] = False
                    else:
                        new_closed[b] = False
            new_timer_on = {tid: coil_on[tid] for tid in self.timer_on}
            if new_closed == self.closed and new_timer_on == self.timer_on:
                self._uf, self._src = uf, src
                self._potential_cache = None
                self._lamp_state = {c.label: self._energized(c.parts[0], uf, src) for c in self._lamps}
                self._motor_state, self._currents = self._motor(uf, src)
                return
            for tid, on in new_timer_on.items():
                if not on:
                    self.timer_elapsed[tid] = 0.0
            self.closed, self.timer_on = new_closed, new_timer_on
        raise CircuitError("circuit did not settle (relay chatter)")

    def _motor(self, uf, src) -> tuple[str, dict[str, str]]:
        w = self._windings
        if not w:
            return "stopped", {}
        tn = self.netlist.terminal_net
        names = [p.name[0] for p in w]  # "U1-U2" -> "U"
        lines = [uf.find(tn[p.a]) for p in w]
        ends = [uf.find(tn[p.b]) for p in w]
        phase = [self._phase(r, src) for r in lines]
        phase = [ph if ph in self.netlist.phases else None for ph in phase]
        intact = [self._part_fault.get(p.id) != "open" for p in w]
        zero = {n: "zero" for n in names}
        forward = tuple(phase) in FORWARD_SEQUENCES
        direction = "forward" if forward else "reverse"

        star = ends[0] == ends[1] == ends[2] and not src.get(ends[0])
        delta = all(ends[i] == lines[(i + 1) % 3] for i in range(3))

        if star:
            live = [i for i in range(3) if phase[i] and intact[i]]
            distinct = {phase[i] for i in live}
            if len(live) == 3 and len(distinct) == 3:
                return f"star_{direction}", {n: "nominal" for n in names}
            if len(distinct) >= 2:
                return "humming", {names[i]: "overcurrent" if i in live else "zero" for i in range(3)}
            return "stopped", zero

        if delta:
            # winding i sits between line i and line i+1
            energ = [
                bool(intact[i] and phase[i] and phase[(i + 1) % 3] and phase[i] != phase[(i + 1) % 3])
                for i in range(3)
            ]
            distinct = {ph for ph in phase if ph}
            if len(distinct) == 3 and sum(energ) >= 2:
                if all(energ):
                    return f"delta_{direction}", {n: "nominal" for n in names}
                # open delta: the line feeding both healthy windings carries more current
                cur = {}
                for i in range(3):
                    k = energ[i] + energ[i - 1]
                    cur[names[i]] = "overcurrent" if k == 2 else "nominal" if k == 1 else "zero"
                return f"delta_{direction}", cur
            if len(distinct) >= 2 and any(energ):
                return "humming", {names[i]: "overcurrent" if phase[i] else "zero" for i in range(3)}
            return "stopped", zero

        return "stopped", zero

    def _tick(self, dt: float) -> None:
        self.time += dt
        for tid, on in self.timer_on.items():
            if on:
                self.timer_elapsed[tid] += dt
        overcurrent = any(v == "overcurrent" for v in self._currents.values())
        for kid in self.thermal_heat:
            heat = self.thermal_heat[kid] + dt if overcurrent else max(0.0, self.thermal_heat[kid] - dt)
            self.thermal_heat[kid] = heat
            trip_time = float(self.netlist.components[kid].params.get("trip_time", 8.0))
            if heat >= trip_time - 1e-6 and not self.tripped[kid]:
                self.tripped[kid] = True
                self.events.append(f"t={self.time:.1f}s {kid} tripped on overload")
        self._settle()

    def _roots(self) -> set:
        return {self._uf.find(n) for n in self.netlist.nets}

    def _load_edges(self) -> list[tuple[str, str, float]]:
        tn = self.netlist.terminal_net
        edges = []
        for p in self._load_parts:
            if self._part_fault.get(p.id) in ("open", "short"):
                continue
            edges.append((self._uf.find(tn[p.a]), self._uf.find(tn[p.b]), 1.0 / p.resistance))
        return edges
