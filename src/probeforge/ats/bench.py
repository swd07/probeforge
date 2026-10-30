"""The ATS bench simulator: electrical state, transfer switch mechanism, generator, UPS and the Group G controller.

Documented (978741 and the Group G Controller User's Guide 381333-400 N):
- the circuit itself (scenarios/circuits/asco_300g_978741.yaml);
- the TS control (cut-off) contact table: 8-9 and 71-72 closed on Normal and before top dead center toward
  Emergency, 6-7 and 69-70 closed on Emergency and before top dead center toward Normal;
- the 3ATS sequence (guide pages 29, 30): on a normal source failure the controller de-energizes SE and starts
  Feature 1C; when 1C ends it de-energizes NR (engine start signal); when the emergency source is accepted it runs
  Feature 2B, then energizes ER, the TS coil operates and every contact reverses. Retransfer: Feature 3A, then ER off
  and SE on, then the Feature 2E cooldown, then NR on (engine stop signal);
- source acceptability (guide page 7) with the default pickup / dropout settings and timers (pages 14, 16);
- the status lights, display messages and logged event types (pages 6, 26 to 28, 43, 44).

Assumed (listed in ASSUMPTIONS, shown in docs/ATS_MODEL.md, to be confirmed by the electrical engineer): mechanism
travel and coil pickup, the generator start curve, when Transfer Failure and Position Error are declared, the coil
burnout time, the UPS autonomy. Frequency is not simulated (sources are at nominal frequency when they have voltage).
"""

import math
from dataclasses import dataclass, field

from probeforge.faults.model import Fault
from probeforge.sim.netlist import Netlist
from probeforge.sim.solver import UnionFind, node_potentials

# --- documented settings (guide pages 14 and 16, factory defaults); percentages of nominal
SETTINGS = {
    "nominal_v": 208.0,  # line to line, 3 phase 4 wire (catalog / cover sheet)
    "n_dropout": 0.85, "n_pickup": 0.90,
    "e_dropout": 0.75, "e_pickup": 0.90,
    "t_1c": 3.0,  # override momentary Normal source outages
    "t_1f": 4.0,  # override momentary Emergency source outages
    "t_2b": 0.0,  # transfer to Emergency
    "t_3a": 1800.0,  # retransfer to Normal (if Normal failed), 30 min
    "t_2e": 300.0,  # engine cooldown, 5 min
}

# --- assumptions (not documented); every value here is a simulation parameter for the engineer to confirm
ASSUMPTIONS = {
    "travel_s": 0.15,  # mechanism travel Normal <-> Emergency (open transition); top dead center at half travel
    "coil_pickup": 0.70,  # TS coil operates above this share of nominal voltage across A-B
    "fallback_before_tdc": True,  # coil released before top dead center: the mechanism falls back
    "gen_crank_s": 2.0,  # generator cranking before voltage builds
    "gen_rated_s": 10.0,  # rated voltage this long after the start signal (guide: "usually about 10 seconds")
    "t_transfer_failure": 6.0,  # Transfer Failure if the position does not change this long after the command
    "t_position_error": 2.0,  # Position Error if 14A / 14B disagree with the position this long without a command
    "coil_burnout_s": 30.0,  # a coil energized continuously this long burns open
    "ups_autonomy_s": 600.0,  # UPS autonomy (simulation parameter, labelled in the UI)
    # with both sources isolated the switch can be operated manually for a check (maintenance operation; 978741
    # sheet 3 only says a test and adjustment procedure sets the cut-off contacts): a jammed mechanism does not move
    "manual_operation_isolated": True,
}

PHASES = {"A": 0.0, "B": -120.0, "C": 120.0}
SENSE_N = ("CP:J12", "CP:J11", "CP:J4")  # NA, NB, NC (978741 sheet 4)
SENSE_E = ("CP:J7", "CP:J18", "CP:J6")  # EA, EB, EC (3 phase with accessory 11BE)
POS_COMMON, POS_14B, POS_14A = "CP:J10", "CP:J13", "CP:J14"
LOAD = ("TS:20", "TS:21", "TS:22")  # LA, LB, LC
INTERNAL_NETS = ("CPX1", "CPX2")  # inside the controller: no probe access
# repairs an authorized person can make (approval tier in the ATS policy), by the part kinds they restore
REPAIR_KINDS = {
    "replace_coil": ("solenoid",),
    "repair_wire": ("wire",),
    "repair_connector": ("pin",),
    "replace_cutoff_contact": ("cutoff_n", "cutoff_e"),
    "adjust_cutoff_contact": ("cutoff_n", "cutoff_e"),
    "replace_controller": ("controller",),
}
CONTROLLER_PARTS = ("SE", "ER", "NR", "CP")  # the relays are inside the controller: replaced with it


def _phasor(volts: float, deg: float) -> complex:
    return volts * complex(math.cos(math.radians(deg)), math.sin(math.radians(deg)))


@dataclass
class Controller:
    """Group G controller state (documented sequence, assumed fault detection)."""

    se: bool = True  # SE energized with the switch on Normal (transfer to Normal path armed)
    er: bool = False
    nr: bool = True  # NR energized: engine start signal off
    n_ok: bool = True
    e_ok: bool = False
    stage: str = "normal"
    timer: float = 0.0  # time spent in the current timed stage
    e_low: float = 0.0  # time the emergency source has been below dropout (Feature 1F)
    command_t: float = 0.0  # time since the last transfer command
    alarms: list[str] = field(default_factory=list)
    pos_err_t: float = 0.0
    display: str = "Load on Normal"


class AtsBench:
    def __init__(self, netlist: Netlist | None = None, faults: list[Fault] | None = None,
                 settings: dict | None = None, assumptions: dict | None = None):
        from pathlib import Path

        self.n = netlist or Netlist.load(Path(__file__).resolve().parents[3] / "scenarios" / "circuits" / "asco_300g_978741.yaml")
        self.s = {**SETTINGS, **(settings or {})}
        self.a = {**ASSUMPTIONS, **(assumptions or {})}
        self.faults: list[Fault] = []
        self.t = 0.0
        self.utility_on = True
        self.position = "N"  # mechanical position: "N" or "E"
        self.moving: str | None = None  # "toE" / "toN" while travelling
        self.progress = 0.0  # share of travel done
        self.gen_t: float | None = None  # time since the start signal (None: engine stopped)
        self.gen_locked = False  # generator locked out (isolation for resistance checks)
        self.isolated = False
        self._utility_before_isolation = True
        self.coil_on_t = 0.0  # continuous energization of the TS coil
        self.coil_burnt = False
        self.ctl = Controller()
        self.events: list[tuple[float, str, str]] = []
        self.ups_left = self.a["ups_autonomy_s"]
        self.ups_draining = False
        self.outage_t: float | None = None
        for f in faults or []:
            self.apply_fault(f)
        self._settle()

    # ------------------------------------------------------------------ faults

    def apply_fault(self, fault: Fault) -> None:
        from probeforge.ats.faults import validate

        validate(self.n, fault)
        self.faults.append(fault)
        if fault.mode == "burnt" and fault.part == "A-B":
            self.coil_burnt = True

    def _fault(self, component: str, part: str | None, *modes: str) -> bool:
        return any(f.component == component and f.part == part and f.mode in modes for f in self.faults)

    # ------------------------------------------------------------------ mechanism

    def _cutoff_closed(self, kind: str) -> bool:
        """Cut-off contact state from the sheet 3 table, by position and travel."""
        before_tdc = self.progress < 0.5
        if kind == "cutoff_n":  # 8-9, 71-72: closed on Normal and before TDC toward Emergency
            return (self.position == "N" and self.moving is None) or (self.moving == "toE" and before_tdc)
        return (self.position == "E" and self.moving is None) or (self.moving == "toN" and before_tdc)

    def _conducts(self, p) -> bool:
        comp, k = p.component, p.kind
        if self._fault(comp, p.name, "open", "stuck_open"):
            return False
        if self._fault(comp, p.name, "stuck_closed"):  # for a cut-off: does not open at top dead center
            return True
        if k in ("wire", "pin", "breaker_pole"):
            return True
        if k == "main_n":
            return self.position == "N" and self.moving is None
        if k == "main_e":
            return self.position == "E" and self.moving is None
        if k in ("cutoff_n", "cutoff_e"):
            return self._cutoff_closed(k)
        if k == "aux_n":
            return self.position == "N" and self.moving is None
        if k == "aux_e":
            return self.position == "E" and self.moving is None
        if k in ("contact_no", "contact_nc"):
            energized = {"SE": self.ctl.se, "ER": self.ctl.er, "NR": self.ctl.nr}[comp]
            return energized == (k == "contact_no")
        return False

    # ------------------------------------------------------------------ electrical state

    def _gen_fraction(self) -> float:
        if self.gen_t is None:
            return 0.0
        crank, rated = self.a["gen_crank_s"], self.a["gen_rated_s"]
        return max(0.0, min(1.0, (self.gen_t - crank) / (rated - crank)))

    def _solve(self) -> None:
        n = self.n
        uf = UnionFind(n.nets)
        for p in n.parts.values():
            if p.kind not in ("solenoid", "input", "point") and self._conducts(p):
                uf.union(n.terminal_net[p.a], n.terminal_net[p.b])
        fixed: dict = {}
        v_ph = self.s["nominal_v"] / math.sqrt(3)
        if self.utility_on:
            for ph, net in zip(PHASES, ("UA", "UB", "UC")):
                fixed[uf.find(net)] = _phasor(v_ph, PHASES[ph])
        frac = self._gen_fraction()
        if frac > 0:
            for ph, net in zip(PHASES, ("EA", "EB", "EC")):
                fixed.setdefault(uf.find(net), _phasor(v_ph * frac, PHASES[ph]))
        for net in ("NN", "EN"):  # neutrals bonded to earth (service entrance, outline one-line diagram)
            fixed.setdefault(uf.find(net), 0j)
        edges = []
        coil = n.parts["TS:A-B"]
        if not (self.coil_burnt or self._fault("TS", "A-B", "open")):
            edges.append((uf.find(n.terminal_net[coil.a]), uf.find(n.terminal_net[coil.b]), 1.0 / coil.resistance))
        roots = {uf.find(x) for x in n.nets}
        self._uf, self._pot = uf, node_potentials(roots, edges, fixed)

    def _v(self, point: str) -> complex | None:
        return self._pot[self._uf.find(self.n.terminal_net.get(point, point))]

    def voltage(self, a: str, b: str) -> float:
        """RMS voltmeter reading between two probe points (terminal ids or net names); 0 if either floats."""
        va, vb = self._v(a), self._v(b)
        return 0.0 if va is None or vb is None else round(abs(va - vb), 1)

    def connected(self, a: str, b: str) -> bool:
        return self._uf.find(self.n.terminal_net.get(a, a)) == self._uf.find(self.n.terminal_net.get(b, b))

    def resistance(self, a: str, b: str) -> float:
        """Ohmmeter reading with both sources isolated (passive network); math.inf when open. The policy decides
        when this may be used."""
        ra, rb = self._uf.find(self.n.terminal_net.get(a, a)), self._uf.find(self.n.terminal_net.get(b, b))
        if ra == rb:
            return 0.0
        coil = self.n.parts["TS:A-B"]
        edges = []
        if not (self.coil_burnt or self._fault("TS", "A-B", "open")):
            edges.append((self._uf.find(self.n.terminal_net[coil.a]), self._uf.find(self.n.terminal_net[coil.b]),
                          1.0 / coil.resistance))
        roots = {self._uf.find(x) for x in self.n.nets}
        pot = node_potentials(roots, edges, {rb: 0j}, {ra: 1.0})
        return math.inf if pot[ra] is None else round(pot[ra].real, 1)

    def _input(self, terminal: str) -> bool:
        """A controller input works unless it failed (then the controller reads nothing on it)."""
        comp, _, name = terminal.partition(":")
        return not self._fault(comp, name, "open")

    def _ll(self, points) -> list[float]:
        vs = [self._v(p) if self._input(p) else None for p in points]
        return [0.0 if (x is None or y is None) else abs(x - y) for x, y in zip(vs, vs[1:] + vs[:1])]

    def coil_voltage(self) -> float:
        return self.voltage("TS:A", "TS:B")

    def coil_energized(self) -> bool:
        if self.coil_burnt or self._fault("TS", "A-B", "open"):
            return False
        return self.coil_voltage() >= self.a["coil_pickup"] * self.s["nominal_v"]

    def load_voltage(self) -> float:
        return min(self._ll(LOAD))

    def position_seen(self) -> str:
        """What the controller reads from TS 14A / 14B (sheet 4): 'N', 'E' or 'unknown'."""
        ok = self._input(POS_COMMON)
        a = ok and self._input(POS_14A) and self.connected(POS_COMMON, POS_14A)
        b = ok and self._input(POS_14B) and self.connected(POS_COMMON, POS_14B)
        return "N" if a and not b else "E" if b and not a else "unknown"

    # ------------------------------------------------------------------ public API

    def lose_utility(self) -> None:
        self.utility_on = False
        if self.outage_t is None:
            self.outage_t = self.t
        self._settle()

    def restore_utility(self) -> None:
        self.utility_on = True
        self._settle()

    def isolate(self) -> None:
        """Both sources isolated for resistance checks: utility off and the generator locked out. The switch stays
        where it is; the controller's relays drop out with no supply (assumed)."""
        if self.isolated:
            return
        self._utility_before_isolation = self.utility_on
        self.utility_on = False
        self.gen_locked = True
        self.isolated = True
        self.gen_t = None
        self.ctl.se = self.ctl.er = self.ctl.nr = False
        self._solve()

    def deisolate(self) -> None:
        """Remove the isolation: the utility side returns to its state before (still lost during an outage), the
        generator lock-out is removed and the controller powers up and restarts its automatic sequence, which repeats
        the transfer attempt (assumed: active alarms clear on power-up, the event log is kept)."""
        if not self.isolated:
            return
        self.isolated = self.gen_locked = False
        self.utility_on = self._utility_before_isolation
        self.ctl = Controller()
        self._settle()

    def retry_transfer(self) -> None:
        """The operator resets the alarm and the controller repeats the failed transfer command: ER drops and
        energizes again, a new operation of the TS coil (assumed; the guide's HELP for Transfer Failure is missing)."""
        c = self.ctl
        if self.isolated:
            raise RuntimeError("both sources are isolated: no transfer command possible")
        if c.stage not in ("transfer_failure", "position_error"):
            raise RuntimeError("no failed transfer to repeat")
        if not c.e_ok:
            raise RuntimeError("the Emergency source is not accepted: the controller cannot command a transfer")
        c.alarms = [x for x in c.alarms if x not in ("Transfer Failure", "Position Error")]
        c.er, c.se, c.stage, c.command_t = True, False, "transferring", 0.0
        self.coil_on_t = 0.0  # ER dropped and energized again: a new energization of the coil
        self._settle()

    def repair_target(self, action: str, target: str) -> tuple[str, str | None]:
        """Resolve a repair target to (component, part) or raise ValueError. replace_controller takes 'CP'."""
        kinds = REPAIR_KINDS.get(action)
        if kinds is None:
            raise ValueError(f"unknown repair {action!r}")
        if action == "replace_controller":
            if target.strip().upper() not in ("CP", ""):
                raise ValueError("replace_controller takes target 'CP'")
            return "CP", None
        part = self.n.parts.get(target.strip())
        if part is None or part.kind not in kinds:
            what = {"replace_coil": "the TS solenoid", "repair_wire": "a harness wire", "repair_connector": "a plug/jack pin"}
            raise ValueError(f"{action} needs the part id of {what.get(action, 'a TS cut-off contact')} (see get_schematic)")
        return part.component, part.name

    def repair(self, action: str, target: str) -> None:
        """An authorized repair with both sources isolated. It restores the part named, nothing else: a replaced
        coil burns again if the cut-off contact that burnt it is still faulty."""
        if not self.isolated:
            raise RuntimeError("repairs only with both sources isolated")
        comp, part = self.repair_target(action, target)
        if action == "replace_controller":
            self.faults = [f for f in self.faults if f.component not in CONTROLLER_PARTS]
            return
        self.faults = [f for f in self.faults if not (f.component == comp and f.part == part)]
        if action == "replace_coil":
            self.coil_burnt, self.coil_on_t = False, 0.0
        self._solve()

    def step(self, dt: float) -> None:
        """Advance virtual time: small ticks while something moves or ramps, larger jumps in between."""
        end = self.t + dt
        while self.t < end - 1e-9:
            h = min(self._tick_size(), end - self.t)
            self._advance(h)

    def manual_operate(self) -> bool:
        """Operate the switch manually to the other position with both sources isolated (assumed maintenance check).
        Returns False if the mechanism does not move (jammed)."""
        if not (self.isolated and self.a["manual_operation_isolated"]):
            raise RuntimeError("manual operation only with both sources isolated")
        if self._fault("TS", None, "jammed"):
            return False
        self.position = "E" if self.position == "N" else "N"
        self._solve()
        return True

    def indicators(self) -> dict:
        c = self.ctl
        seen = self.position_seen()
        return {
            "lights": {"Normal accepted": c.n_ok, "Emergency accepted": c.e_ok, "Load on Normal": seen == "N",
                       "Load on Emergency": seen == "E", "Alert": bool(c.alarms), "Not in automatic": False},
            "display": c.display,
            # metering screen (guide page 7): rms voltages as the controller measures them, line to line A-B, B-C, C-A
            # (3 phase Emergency sensing with accessory 11BE); a failed input or open sensing wire reads 0
            "metering": {"Normal": [round(v) for v in self._ll(SENSE_N)], "Emergency": [round(v) for v in self._ll(SENSE_E)]},
            "alarms": list(c.alarms),
            "events": [{"t": round(t, 1), "event": e, "cause": cause} for t, e, cause in self.events],
            "normal_source": "available" if self.utility_on else "lost",
            "generator": self.generator_state(),
            "load_powered": self.load_voltage() >= 0.9 * self.s["nominal_v"],
            "ups": {"autonomy_s": self.a["ups_autonomy_s"], "left_s": round(self.ups_left, 1),
                    "draining": self.ups_draining, "depleted": self.ups_left <= 0},
            "time_s": round(self.t, 1),
        }

    def generator_state(self) -> str:
        if self.gen_t is None:
            return "stopped"
        frac = self._gen_fraction()
        return "cranking" if frac == 0 else "running" if frac >= 1 else "running up"

    def clone(self) -> "AtsBench":
        import copy

        c = copy.copy(self)
        c.ctl = copy.deepcopy(self.ctl)
        c.events = list(self.events)
        c.faults = list(self.faults)
        return c

    # ------------------------------------------------------------------ simulation

    def _tick_size(self) -> float:
        c = self.ctl
        if self.moving:
            return 0.01
        busy = ("n_fail_timer", "waiting_e", "timer_2b", "transferring", "retransferring")
        if self.gen_t is not None and self._gen_fraction() < 1 or c.stage in busy or self.coil_energized():
            return 0.05
        return 1.0

    def _log(self, event: str, cause: str = "") -> None:
        self.events.append((self.t, event, cause))

    def _settle(self) -> None:
        self._solve()
        self._control(0.0)
        self._solve()

    def _advance(self, h: float) -> None:
        self.t += h
        # generator: runs while the TB/TS 14-15 start contact is closed (Feature 7 closes to start, assumed wiring)
        start = self.connected("TBTS:14", "TBTS:15") and not self.gen_locked
        if start and self.gen_t is None:
            self.gen_t = h  # the start contact closed at the end of the previous tick
        elif start:
            self.gen_t += h
        elif not start:
            self.gen_t = None
        self._solve()
        # TS coil and mechanism
        if self.coil_energized():
            # one operation per energization: a coil that stays energized holds the plunger, it does not move the
            # mechanism back (assumed solenoid behaviour)
            if self.coil_on_t == 0.0 and self.moving is None and not self._fault("TS", None, "jammed"):
                self.moving, self.progress = ("toE" if self.position == "N" else "toN"), 0.0
            self.coil_on_t += h
            if self.coil_on_t >= self.a["coil_burnout_s"]:
                self.coil_burnt = True
        else:
            self.coil_on_t = 0.0
        if self.moving:
            if self.coil_energized() or self.progress >= 0.5 or not self.a["fallback_before_tdc"]:
                self.progress += h / self.a["travel_s"]
                if self.progress >= 1.0:
                    self.position = "E" if self.moving == "toE" else "N"
                    self.moving, self.progress = None, 0.0
            else:
                self.moving, self.progress = None, 0.0  # released before top dead center: falls back
        self._solve()
        self._control(h)
        self._solve()
        # UPS: drains while the load has no voltage
        self.ups_draining = self.load_voltage() < 0.9 * self.s["nominal_v"]
        if self.ups_draining:
            self.ups_left = max(0.0, self.ups_left - h)

    def _control(self, h: float) -> None:
        """Group G 3ATS sequence (documented) with assumed fault detection."""
        c, s, a = self.ctl, self.s, self.a
        nom = s["nominal_v"]
        n_v, e_v = min(self._ll(SENSE_N)), min(self._ll(SENSE_E))
        n_low, n_high = n_v < s["n_dropout"] * nom, n_v >= s["n_pickup"] * nom
        e_ok_before = c.e_ok
        if c.e_ok:
            c.e_low = c.e_low + h if e_v < s["e_dropout"] * nom else 0.0
            if c.e_low > s["t_1f"]:
                c.e_ok = False
                self._log("E Source Not Accepted", "E Under Voltage")
        elif e_v >= s["e_pickup"] * nom:
            c.e_ok, c.e_low = True, 0.0
            self._log("E Source Accepted")
        c.timer += h
        c.command_t += h
        seen = self.position_seen()

        if c.stage == "normal":
            if n_low:  # normal source failure: SE drops out, Feature 1C starts (guide page 29)
                c.se, c.stage, c.timer = False, "n_fail_timer", 0.0
            c.display = "Load on Normal" if seen == "N" else c.display
        elif c.stage == "n_fail_timer":
            if n_high:  # restored during 1C: SE re-energized, sequence terminated
                c.se, c.stage = True, "normal"
            elif c.timer >= s["t_1c"]:
                c.n_ok = False
                self._log("N Source Not Accepted", "N Under Voltage")
                c.nr, c.stage, c.timer = False, "waiting_e", 0.0  # NR drops out: engine start signal
                self._log("Engine Start")
            c.display = "Normal Fail Timer"
        elif c.stage == "waiting_e":
            if c.e_ok:
                c.stage, c.timer = "timer_2b", 0.0
            c.display = "Waiting for Emergency Acceptable"
        if c.stage == "timer_2b":
            if not c.e_ok:
                c.stage, c.timer = "waiting_e", 0.0
            elif c.timer >= s["t_2b"]:
                c.er, c.stage, c.command_t = True, "transferring", 0.0  # ER energizes: TS coil operates
            else:
                c.display = "Normal to Emergency Timer"
        if c.stage == "transferring":
            c.display = "Transfer to Emergency"
            if seen == "E":
                c.stage = "on_e"
                self._log("Transfer N to E", "N Not Accepted")
            elif c.command_t >= a["t_transfer_failure"]:  # assumed detection (the guide's HELP section is missing)
                self._failed("N")
        if c.stage in ("transfer_failure", "position_error"):  # assumed: ER / SE stay as commanded, no automatic retry
            c.display = "Transfer Failure" if c.stage == "transfer_failure" else "Position Error"
        if c.stage == "on_e":
            c.display = "Load on Emergency"
            if n_high and self.utility_on:
                c.stage, c.timer = "timer_3a", 0.0
                c.n_ok = True
                self._log("N Source Accepted")
        if c.stage == "timer_3a":
            c.display = "Emergency to Normal Timer"
            if not n_high:
                c.stage, c.n_ok = "on_e", False
            elif c.timer >= s["t_3a"]:
                c.er, c.se, c.stage, c.command_t = False, True, "retransferring", 0.0  # ER off, SE on
        if c.stage == "retransferring":
            c.display = "Transfer to Normal"
            if seen == "N":
                c.stage, c.timer = "cooldown_2e", 0.0
                self._log("Transfer E to N", "N Source Accepted")
            elif c.command_t >= a["t_transfer_failure"]:
                self._failed("E")
        if c.stage == "cooldown_2e":
            c.display = "Engine Cooldown Timer"
            if c.timer >= s["t_2e"]:
                c.nr, c.stage = True, "normal"  # NR energizes: engine stop signal
                self._log("Engine Stop")
                c.display = "Load on Normal"
        # position contacts disagreeing with a settled switch and no command running (assumed Position Error)
        settled = c.stage in ("normal", "on_e", "timer_3a", "cooldown_2e", "waiting_e", "n_fail_timer")
        expected = "E" if c.stage in ("on_e", "timer_3a") else "N"
        if settled and seen != expected:
            c.pos_err_t += h
            if c.pos_err_t >= a["t_position_error"] and "Position Error" not in c.alarms:
                c.alarms.append("Position Error")
                self._log("Position Error")
        else:
            c.pos_err_t = 0.0
        del e_ok_before

    def _failed(self, origin: str) -> None:
        """No position confirmation after a transfer command (assumed rule): if the switch never left its origin
        (its position contact is still closed) it is a Transfer Failure; if it left but the other position is never
        confirmed, a Position Error."""
        c = self.ctl
        origin_contact = POS_14A if origin == "N" else POS_14B
        if self.connected(POS_COMMON, origin_contact):
            c.stage = "transfer_failure"
            c.alarms.append("Transfer Failure")
            self._log("Transfer Failure", "Switch on Normal" if origin == "N" else "Switch on Emergency")
        else:
            c.stage = "position_error"
            c.alarms.append("Position Error")
            self._log("Position Error")
