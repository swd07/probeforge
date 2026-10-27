"""Deterministic baseline: golden-twin comparison plus half-split search.

The baseline knows the schematic and what a healthy circuit reads in any state
(a fault-free twin simulation: the electrician's expected value), never the
fault. It uses the same ToolBox and policy as the agent, so measurements,
blocked actions and evidence are counted the same way.

1. Fixed functional test, mirrored on the twin: panel at rest, then for each
   Start button: press, wait 7 s, Stop. The first observation that differs from
   the twin selects a plan. No difference at all: insufficient_information.
2. Plans, in priority order:
   - a protection device operated: power off, compare load resistances (short)
   - humming or a dead motor line: half-split the dead phase from the supply
   - a lamp lit through a thermal relay contact: check the relay's NC side
   - motor runs only while Start is held: the self-hold contact
   - otherwise, in the failing state (button held if needed), check the voltage
     on every load the twin has energized (coils first). The first load missing
     its voltage is half-split along its supply path. A coil that has voltage
     is checked for pull-in on one of its NO contacts.
3. The located part is refined with fixed rules: timer contact -> timer coil
   or stuck timer, contactor NC aux -> welded contactor, thermal NC -> tripped.
4. Nothing located: power off and compare every part's resistance with the
   twin in netlist order (exhaustive, not half-split).
"""

import math
from collections import deque
from contextlib import contextmanager

from probeforge.faults.model import Fault
from probeforge.policy import Policy
from probeforge.sim import Circuit
from probeforge.sim.netlist import LOAD_KINDS, Part
from probeforge.tools.toolbox import Approver, ToolBox, deny_all

TOL_V = 20.0
WAIT_S = 7.0
Diagnosis = tuple[str, str | None, str] | None  # component, part, failure mode


class BaselineStuck(RuntimeError):
    pass


def _approve(request) -> bool:
    return True


def _ohms(value) -> float:
    return math.inf if value == "open" else float(value)


def _differs(rf: float, rt: float) -> bool:
    if math.isinf(rf) or math.isinf(rt):
        return math.isinf(rf) != math.isinf(rt)
    return abs(rf - rt) > max(1.0, 0.02 * rt)


class HalfSplitBaseline:
    def __init__(self, circuit: Circuit, approver: Approver = deny_all):
        self.n = circuit.netlist
        self.tn = self.n.terminal_net
        self.tb = ToolBox(circuit, approver=approver)
        self.twin = Circuit(self.n)
        self.twin.set_power(circuit.power)
        self.twin_tb = ToolBox(self.twin, policy=Policy(max_consecutive_starts=10**9), approver=_approve)
        self.start_power = circuit.power
        buttons = self.n.components_of("button")
        self.stop = next(b.id for b in buttons if b.label.lower().startswith("stop"))
        self.starts = [b.id for b in buttons if b.label.lower().startswith("start")]
        self.hold_button: str | None = None  # probes are taken while this button is held
        self.recipe: list[tuple] = []  # actions applied so far, to replay what-if circuits
        self.evidence: list[dict] = []
        self.notes: list[str] = []
        self.view_f: dict = {}
        self.view_t: dict = {}

    # ------------------------------------------------------------------ public

    def run(self) -> dict:
        self.tb.initial_observation()
        try:
            found = self._diagnose()
        except BaselineStuck as e:
            self.notes.append(f"stuck: {e}")
            found = None
        evidence = self.evidence[-6:] or [{"step": 0, "type": "functional_test", "observation": "panel at rest"}]
        if found is None:
            args = {"outcome": "insufficient_information", "confidence": 0.0, "evidence": evidence}
        else:
            comp, part, mode = found
            args = {"outcome": "diagnosed", "component": comp, "part": part or "", "failure_mode": mode,
                    "confidence": 0.9, "evidence": evidence}
        result = self.tb.call("submit_diagnosis", args)
        if "error" in result:
            raise RuntimeError(f"baseline diagnosis rejected: {result['error']}")
        return self.tb.diagnosis

    # ---------------------------------------------------------------- acting

    def act(self, tool: str, args: dict) -> tuple[dict, dict]:
        f = self.tb.call(tool, args)
        if "error" in f:
            raise BaselineStuck(f"{tool}: {f['error']}")
        t = self.twin_tb.call(tool, args)
        if tool == "press_button":
            self.recipe.append(("press", args["button"], args.get("hold_seconds", 0.2)))
        elif tool == "wait":
            self.recipe.append(("wait", args["seconds"]))
        elif tool == "set_power":
            self.recipe.append(("power", args["on"]))
        return f, t

    @staticmethod
    def view(r: dict) -> dict:
        r = r.get("after_release", r)
        return {k: r[k] for k in ("lamps", "motor", "line_currents", "line_currents_a", "power_switch")}

    def functional(self, step: int, text: str) -> None:
        self.evidence.append({"step": step, "type": "functional_test", "observation": text})

    def probe(self, a: str, b: str | None = None) -> tuple[float, float]:
        """Voltage a-b on the faulty panel and on the twin, in the current plan state."""
        b = b or self.n.neutral
        if self.hold_button:
            args = {"button": self.hold_button, "hold_seconds": 0.5, "measure_while_held": [{"point_a": a, "point_b": b}]}
            f, t = self.act("press_button", args)
            self.act("press_button", {"button": self.stop})
            vf, vt = f["readings"][0]["volts"], t["readings"][0]["volts"]
        else:
            f, t = self.act("measure_voltage", {"point_a": a, "point_b": b})
            vf, vt = f["volts"], t["volts"]
        self.evidence.append({"step": f["step"], "type": "instrument_reading",
                              "observation": f"{a} to {b}: {vf} V, healthy {vt} V"})
        return vf, vt

    def ohms(self, a: str, b: str) -> tuple[float, float]:
        if self.tb.panel().power_on:
            self.act("set_power", {"on": False})
        f, t = self.act("measure_resistance", {"point_a": a, "point_b": b})
        rf, rt = _ohms(f["ohms"]), _ohms(t["ohms"])
        self.evidence.append({"step": f["step"], "type": "instrument_reading",
                              "observation": f"{a} to {b}: {f['ohms']} ohm, healthy {t['ohms']} ohm"})
        return rf, rt

    @contextmanager
    def twin_in_state(self):
        """Put the twin into the plan state (button held) for path and expectation queries."""
        if not self.hold_button:
            yield
            return
        self.twin.hold(self.hold_button)
        try:
            yield
        finally:
            self.twin.release(self.hold_button)
            self.twin.hold(self.stop)
            self.twin.release(self.stop)

    def replay(self, fault: Fault | None) -> Circuit:
        """A fresh circuit (optionally with a hypothetical fault) driven through the same actions."""
        c = Circuit(self.n)
        if fault:
            c.apply_fault(fault)
        c.set_power(self.start_power)
        for op, *arg in self.recipe:
            if op == "press":
                c.press(arg[0], arg[1])
            elif op == "wait":
                c.step(arg[0])
            elif op == "power":
                c.set_power(arg[0])
        if self.hold_button:
            c.hold(self.hold_button)
        return c

    # ------------------------------------------------------------- top level

    def _diagnose(self) -> Diagnosis:
        f, t = self.act("read_indicators", {})
        if self.view(f) != self.view(t):
            return self.plan(f, t, None)
        for start in self.starts:
            for tool, args in (("press_button", {"button": start}), ("wait", {"seconds": WAIT_S}),
                               ("press_button", {"button": self.stop})):
                f, t = self.act(tool, args)
                if self.view(f) != self.view(t) or ("note" in f) != ("note" in t):
                    return self.plan(f, t, args.get("button"))
        self.notes.append("functional test matches a healthy panel")
        return None

    def plan(self, f: dict, t: dict, pressed: str | None) -> Diagnosis:
        fv, tv = self.view(f), self.view(t)
        self.view_f, self.view_t = fv, tv
        self.functional(f["step"], f"panel differs from healthy: motor {fv['motor']} (healthy {tv['motor']}), "
                                   f"lamps {fv['lamps']} (healthy {tv['lamps']})")
        if "note" in f and "note" not in t:
            self.notes.append("plan: short circuit")
            return self.plan_short()
        currents = set(fv["line_currents"].values())
        if fv["motor"] == "humming" or {"zero", "overcurrent"} <= currents:
            self.notes.append("plan: power circuit phase")
            return self.plan_power(fv)
        for label, on in fv["lamps"].items():
            if on and not tv["lamps"][label]:
                kk = self.thermal_feeding_lamp(label)
                if kk:
                    self.notes.append("plan: thermal relay")
                    return self.plan_thermal(kk)
        if pressed in self.starts and fv["motor"] == "stopped" and tv["motor"] != "stopped":
            self.notes.append(f"plan: start {pressed}")
            return self.plan_start(pressed)
        self.notes.append("plan: loads in current state")
        return self.plan_loads() or self.plan_exhaustive()

    # ------------------------------------------------------------------ plans

    def plan_start(self, button: str) -> Diagnosis:
        f, t = self.act("press_button", {"button": button, "hold_seconds": 1.0})
        self.act("press_button", {"button": self.stop})
        held_f, held_t = f["while_held"], t["while_held"]
        self.functional(f["step"], f"while held: motor {held_f['motor']} (healthy {held_t['motor']})")
        if held_f["motor"] == held_t["motor"] != "stopped":
            hold = self.self_hold_part(button)
            if hold:
                return hold.component, hold.name, "stuck_open"
        self.view_f, self.view_t = self.view(held_f), self.view(held_t)
        self.hold_button = button
        try:
            return self.plan_loads() or self.plan_exhaustive()
        finally:
            self.hold_button = None

    def plan_loads(self) -> Diagnosis:
        with self.twin_in_state():
            loads = [self.n.parts[pid] for pid in self.twin.energized_loads()]
        loads.sort(key=lambda p: p.kind != "coil")
        for load in loads:
            vf, vt = self.probe(load.a, load.b)
            if vt - vf > TOL_V:
                return self.refine(self.split(load), load)
            comp = self.n.components[load.component]
            if load.kind == "coil" and comp.type == "contactor":
                verdict = self.pull_in_check(comp.id)
                if verdict:
                    return verdict
            if load.kind == "lamp" and self.view_t["lamps"].get(comp.label) and not self.view_f["lamps"].get(comp.label):
                return comp.id, load.name, "open"
        return None

    def plan_power(self, fv: dict) -> Diagnosis:
        dead = [line for line, cur in fv["line_currents"].items() if cur == "zero"]
        windings = self.n.components_of("motor")[0].parts
        winding = next((w for w in windings if dead and w.name.startswith(dead[0])), None)
        if winding is None:
            return self.plan_exhaustive()
        found = self.split(winding)
        if found is winding:
            rf, rt = self.ohms(winding.a, winding.b)
            return (winding.component, winding.name, "open") if _differs(rf, rt) else self.plan_exhaustive()
        return self.refine(found, winding)

    def plan_short(self) -> Diagnosis:
        loads = [self.n.parts[pid] for pid in self.twin.energized_loads()]
        loads.sort(key=lambda p: p.kind != "coil")
        for load in loads:
            rf, rt = self.ohms(load.a, load.b)
            if rf < 0.5 * rt:
                return load.component, load.name, "short"
        return self.plan_exhaustive()

    def plan_thermal(self, kk: str) -> Diagnosis:
        parts = self.n.components[kk].parts
        nc = next(p for p in parts if p.kind == "contact_nc")
        no = next(p for p in parts if p.kind == "contact_no")
        vf, vt = self.probe(nc.b)
        if vt - vf > TOL_V:
            lamp = self.lamp_fed_by(no)
            if lamp is None or self.view_f["lamps"].get(lamp):
                return kk, None, "tripped"
            return kk, nc.name, "stuck_open"  # NC open but the alarm contact did not close
        return kk, no.name, "stuck_closed"

    def plan_exhaustive(self) -> Diagnosis:
        self.notes.append("plan: exhaustive resistance comparison")
        for p in self.n.parts.values():
            rf, rt = self.ohms(p.a, p.b)
            if not _differs(rf, rt):
                continue
            comp = self.n.components[p.component]
            lower = rf < rt
            if comp.type == "thermal_relay" and p.kind != "heater":
                return comp.id, None, "tripped"
            if comp.type == "contactor" and p.kind == "main" and lower:
                others = [q for q in comp.parts if q.kind == "main" and q.id != p.id]
                if others and _differs(*self.ohms(others[0].a, others[0].b)):
                    return comp.id, None, "welded"  # every main pole closed: armature held in
            if p.kind in LOAD_KINDS:
                return comp.id, p.name, "short" if lower else "open"
            if p.kind in ("fuse_pole", "breaker_pole", "heater"):
                return comp.id, p.name, "open"
            return comp.id, p.name, "stuck_closed" if lower else "stuck_open"
        return None

    # ------------------------------------------------------------- half-split

    def supply_path(self, target_net: str) -> tuple[list[str], list[Part]]:
        """Shortest chain of conducting parts (in the twin) from a supply phase to target_net."""
        adj: dict[str, list[tuple[str, Part]]] = {}
        for pid in sorted(self.twin.conducting_parts()):
            p = self.n.parts[pid]
            a, b = self.tn[p.a], self.tn[p.b]
            adj.setdefault(a, []).append((b, p))
            adj.setdefault(b, []).append((a, p))
        prev: dict[str, tuple[str, Part] | None] = {ph: None for ph in self.n.phases}
        queue = deque(self.n.phases)
        while queue:
            u = queue.popleft()
            for v, p in adj.get(u, []):
                if v not in prev:
                    prev[v] = (u, p)
                    queue.append(v)
        if target_net not in prev:
            return [], []
        nets, parts = [target_net], []
        while prev[nets[-1]] is not None:
            u, p = prev[nets[-1]]
            parts.append(p)
            nets.append(u)
        return nets[::-1], parts[::-1]

    def split(self, load: Part) -> Part:
        """Half-split the supply path of a load; returns the open part, or the load itself."""
        with self.twin_in_state():
            nets, parts = self.supply_path(self.tn[load.a])
            conducting = self.twin.conducting_parts()
        if not nets:
            raise BaselineStuck(f"no supply path to {load.id} in the healthy circuit")

        def live(i: int) -> bool:
            vf, vt = self.probe(nets[i])
            return abs(vf - vt) <= TOL_V

        last = len(nets) - 1
        if live(last):
            return load
        lo, hi = 0, last  # nets[0] is a supply phase, assumed live
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if live(mid):
                lo = mid
            else:
                hi = mid
        pair = {nets[lo], nets[hi]}
        alts = [p for p in self.n.parts.values() if p.id in conducting and {self.tn[p.a], self.tn[p.b]} == pair]
        alts.sort(key=lambda p: p.component == load.component)  # self-hold contacts of the load last
        return alts[0] if alts else parts[lo]

    # ----------------------------------------------------------------- refine

    def refine(self, found: Part, load: Part) -> Diagnosis:
        if found.kind in LOAD_KINDS:
            return found.component, found.name, "open"
        comp = self.n.components[found.component]
        if found.kind in ("fuse_pole", "breaker_pole", "heater"):
            return comp.id, found.name, "open"
        if found.kind in ("delayed_no", "delayed_nc"):
            return self.refine_timer(found)
        if comp.type == "contactor" and found.kind == "contact_nc":
            main = next(p for p in comp.parts if p.kind == "main")
            rf, rt = self.ohms(main.a, main.b)
            if rf < 1.0 and rt > 1.0:
                return comp.id, None, "welded"
            return comp.id, found.name, "stuck_open"
        if comp.type == "contactor" and found.kind in ("contact_no", "main"):
            coil = self.coil_of(comp.id)
            vf, vt = self.probe(coil.a, coil.b)
            if vt - vf > TOL_V:
                return self.refine(self.split(coil), coil)
            return self.pull_in_check(comp.id) or (comp.id, found.name, "stuck_open")
        if comp.type == "thermal_relay":
            return self.plan_thermal(comp.id)
        return comp.id, found.name, "stuck_open"

    def refine_timer(self, contact: Part) -> Diagnosis:
        comp = self.n.components[contact.component]
        coil = self.coil_of(comp.id)
        vf, vt = self.probe(coil.a, coil.b)
        if vt - vf > TOL_V:
            return self.refine(self.split(coil), coil)
        others_wrong = False
        for other in comp.parts:
            if other.kind.startswith("delayed") and other.id != contact.id:
                vf, vt = self.probe(other.b)
                others_wrong |= abs(vf - vt) > TOL_V
        # the located contact does not conduct when it should, so the contact candidate is stuck_open
        candidates = [Fault(comp.id, "open", coil.name), Fault(comp.id, "stuck"),
                      Fault(comp.id, "stuck_open", contact.name)]
        predicted = {}
        for cand in candidates:  # what each candidate predicts for the coil resistance, power off
            c = self.replay(cand)
            c.set_power(False)
            predicted[cand] = c.resistance(coil.a, coil.b)
        rf, _ = self.ohms(coil.a, coil.b)
        matching = [cand for cand in candidates if not _differs(rf, predicted[cand])]
        if candidates[0] in matching and len(matching) == 1:
            return comp.id, coil.name, "open"
        if others_wrong and candidates[1] in matching:
            return comp.id, None, "stuck"
        return comp.id, contact.name, "stuck_open"

    # ---------------------------------------------------------------- helpers

    def coil_of(self, cid: str) -> Part:
        return next(p for p in self.n.components[cid].parts if p.kind == "coil")

    def pull_in_check(self, cid: str) -> Diagnosis:
        """Does a contactor whose coil has voltage actually pull in? Probe the NO contacts that
        tell pulled-in from not pulled-in (found with a what-if replay). Two wrong contacts:
        the coil is open. Only one wrong: that contact is stuck open. None wrong: None."""
        coil = self.coil_of(cid)
        what_if = self.replay(Fault(cid, "open", coil.name))
        with self.twin_in_state():
            telling = [c for c in self.n.components[cid].parts if c.kind == "contact_no"
                       and abs(self.twin.voltage(c.a, c.b) - what_if.voltage(c.a, c.b)) > TOL_V]
        wrong = []
        for c in telling[:2]:
            vf, vt = self.probe(c.a, c.b)
            if abs(vf - vt) <= TOL_V:
                break
            wrong.append(c)
        if not wrong:
            return None
        if len(wrong) == 1 and len(telling) > 1:
            return cid, wrong[0].name, "stuck_open"
        return cid, coil.name, "open"

    def self_hold_part(self, button: str) -> Part | None:
        contact = next(p for p in self.n.components[button].parts if p.kind == "contact_no")
        pair = {self.tn[contact.a], self.tn[contact.b]}
        for p in self.n.parts.values():
            comp = self.n.components[p.component]
            if comp.type == "contactor" and p.kind == "contact_no" and {self.tn[p.a], self.tn[p.b]} == pair:
                return p
        return None

    def lamp_fed_by(self, contact: Part) -> str | None:
        """Label of a lamp wired directly behind (on the load side of) a contact."""
        for lamp in self.n.components_of("lamp"):
            if self.tn[lamp.parts[0].a] == self.tn[contact.b]:
                return lamp.label
        return None

    def thermal_feeding_lamp(self, label: str) -> str | None:
        lamp = next((c for c in self.n.components_of("lamp") if c.label == label), None)
        if lamp is None:
            return None
        net = self.tn[lamp.parts[0].a]
        for p in self.n.parts.values():
            if self.n.components[p.component].type == "thermal_relay" and net in (self.tn[p.a], self.tn[p.b]):
                return p.component
        return None
