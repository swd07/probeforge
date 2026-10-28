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
A = cmath.exp(2j * math.pi / 3)  # 120 degree rotation for sequence components
HUMMING_RATIO = 0.7  # negative/positive sequence above this: pulsating field, rotor stalls
UNBALANCED_RATIO = 0.1  # above this: runs, but unbalanced
STAR_DELTA_SPLIT = (1 + 3**0.5) / 2  # positive sequence magnitude between star (1) and delta (sqrt 3)
LOCKED_ROTOR_FACTOR = 6.0  # stalled motor draws about 6x running current
OVERCURRENT_FACTOR = 1.15  # line current above 1.15 x rated counts as overcurrent


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
        self._motor_params = motors[0].params if motors else {}
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
            "line_currents_a": dict(self._amps),
        }

    def voltage(self, a: str, b: str) -> float:
        """RMS voltage a voltmeter would read between two points (terminal or net name)."""
        ra, rb = self._uf.find(self._net_of(a)), self._uf.find(self._net_of(b))
        pot = self._potentials()
        va, vb = pot[ra], pot[rb]
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

    def clone(self) -> "Circuit":
        """Independent copy of the dynamic state (the netlist and the applied faults are shared,
        they never change after apply_fault). Used to predict outcomes without touching the original."""
        c = object.__new__(Circuit)
        c.__dict__.update(self.__dict__)
        c.held = set(self.held)
        c.closed = dict(self.closed)
        c.timer_on = dict(self.timer_on)
        c.timer_elapsed = dict(self.timer_elapsed)
        c.thermal_heat = dict(self.thermal_heat)
        c.tripped = dict(self.tripped)
        c.blown = set(self.blown)
        c.events = list(self.events)
        c._faults = list(self._faults)
        return c

    def net_voltages(self) -> dict[str, float]:
        """Voltage of every net to neutral (0 for floating nets), for visualisation."""
        pot = self._potentials()
        return {net: round(abs(pot[self._uf.find(net)] or 0), 1) for net in self.netlist.nets}

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
                self._motor_state, self._currents, self._amps = self._motor(uf, src)
                return
            for tid, on in new_timer_on.items():
                if not on:
                    self.timer_elapsed[tid] = 0.0
            self.closed, self.timer_on = new_closed, new_timer_on
        raise CircuitError("circuit did not settle (relay chatter)")

    def _motor(self, uf, src) -> tuple[str, dict[str, str], dict[str, float]]:
        """Motor state and line currents from the winding currents.

        Winding currents come from nodal analysis (windings are resistors), in units of the
        rated star winding current. Their positive and negative sequence components give the
        rotating field: one dominant sequence is a running motor (direction from which one),
        both comparable is a pulsating field (humming, rotor stalled, locked-rotor current),
        in between is an unbalanced but running motor. Line currents are the currents leaving
        each motor line terminal into the windings, scaled so a healthy delta run draws the
        rated current.
        """
        w = self._windings
        if not w:
            return "stopped", {}, {}
        tn = self.netlist.terminal_net
        names = [p.name[0] for p in w]  # "U1-U2" -> "U"
        zero = {n: 0.0 for n in names}
        live = any(self._phase(uf.find(tn[t]), src) in self.netlist.phases for p in w for t in (p.a, p.b))
        if not live:
            return "stopped", self._current_labels(zero), zero

        pot = self._potentials()
        unit = self.netlist.voltage / w[0].resistance  # rated star winding current
        cur = []
        for p in w:
            pa, pb = pot[uf.find(tn[p.a])], pot[uf.find(tn[p.b])]
            if self._part_fault.get(p.id) == "open" or pa is None or pb is None:
                cur.append(0j)
            else:
                cur.append((pa - pb) / w[0].resistance / unit)
        pos = abs(cur[0] + A * cur[1] + A * A * cur[2]) / 3
        neg = abs(cur[0] + A * A * cur[1] + A * cur[2]) / 3
        big, small = max(pos, neg), min(pos, neg)
        if sum(abs(c) for c in cur) < 0.05:
            state = "stopped"
        elif big < 0.05 or small / big > HUMMING_RATIO:
            state = "humming"
        else:
            direction = "forward" if pos >= neg else "reverse"
            if small / big > UNBALANCED_RATIO:
                state = f"unbalanced_{direction}"
            else:
                state = f"{'star' if big < STAR_DELTA_SPLIT else 'delta'}_{direction}"

        rated = float(self._motor_params.get("rated_current", 10.0))
        factor = LOCKED_ROTOR_FACTOR if state == "humming" else 1.0
        amps = {}
        line_groups = [uf.find(tn[p.a]) for p in w]
        for k, group in enumerate(line_groups):
            leaving = 0j
            for j, q in enumerate(w):
                if uf.find(tn[q.a]) == group:
                    leaving += cur[j]
                if uf.find(tn[q.b]) == group:
                    leaving -= cur[j]
            leaving /= line_groups.count(group)  # lines tied to the same node share its current
            # a healthy delta line carries 3 units (sqrt(3) x line-voltage winding current)
            amps[names[k]] = round(abs(leaving) * rated / 3 * factor, 1)
        return state, self._current_labels(amps), amps

    def _current_labels(self, amps: dict[str, float]) -> dict[str, str]:
        rated = float(self._motor_params.get("rated_current", 10.0))
        return {
            k: "zero" if a < 0.05 * rated else "overcurrent" if a > OVERCURRENT_FACTOR * rated else "nominal"
            for k, a in amps.items()
        }

    def _potentials(self) -> dict:
        if self._potential_cache is None:
            fixed = {root: self._sources[next(iter(s))] for root, s in self._src.items() if len(s) == 1}
            self._potential_cache = node_potentials(self._roots(), self._load_edges(), fixed)
        return self._potential_cache

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
