"""Load and validate a circuit netlist from YAML."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Which YAML keys a component type may have, and the part kind each key creates.
TYPE_PARTS: dict[str, dict[str, str]] = {
    "breaker": {"poles": "breaker_pole"},
    "fuse": {"poles": "fuse_pole"},
    "button": {"no_contacts": "contact_no", "nc_contacts": "contact_nc"},
    "contactor": {"coil": "coil", "main": "main", "no_contacts": "contact_no", "nc_contacts": "contact_nc"},
    "timer": {
        "coil": "coil",
        "no_contacts": "contact_no",
        "nc_contacts": "contact_nc",
        "no_delayed": "delayed_no",
        "nc_delayed": "delayed_nc",
    },
    "thermal_relay": {"heaters": "heater", "no_contacts": "contact_no", "nc_contacts": "contact_nc"},
    "lamp": {"terminals": "lamp"},
    "motor": {"windings": "winding"},
}

# Parts that carry current through a resistance instead of acting as a switch.
LOAD_KINDS = frozenset({"coil", "lamp", "winding"})

# Contact kinds and whether they conduct when their device is actuated.
CONTACT_KINDS = {
    "contact_no": True,
    "main": True,
    "delayed_no": True,
    "contact_nc": False,
    "delayed_nc": False,
}

DEFAULT_RESISTANCE = {  # ohms
    ("contactor", "coil"): 550.0,
    ("timer", "coil"): 4000.0,
    ("lamp", "lamp"): 2600.0,
    ("motor", "winding"): 3.5,
}

PARAM_KEYS = {"delay", "trip_time", "resistance"}


class NetlistError(ValueError):
    pass


@dataclass(frozen=True)
class Part:
    id: str  # "KM1:13-14"
    component: str  # "KM1"
    name: str  # "13-14"
    kind: str  # one of the part kinds in TYPE_PARTS
    a: str  # terminal id, "KM1:13"
    b: str  # terminal id, "KM1:14"
    resistance: float | None = None  # loads only


@dataclass
class Component:
    id: str
    type: str
    label: str
    parts: list[Part]
    params: dict = field(default_factory=dict)


@dataclass
class Netlist:
    name: str
    title: str
    voltage: float
    phases: dict[str, float]  # phase name -> angle in degrees
    neutral: str
    components: dict[str, Component]
    parts: dict[str, Part]
    nets: dict[str, list[str]]
    terminal_net: dict[str, str]
    power_switch: str
    protection: list[str]
    interlocks: list[tuple[str, str]]
    layout: dict

    @classmethod
    def load(cls, path: str | Path) -> "Netlist":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f))

    @classmethod
    def from_dict(cls, data: dict) -> "Netlist":
        components: dict[str, Component] = {}
        parts: dict[str, Part] = {}
        for cid, spec in data["components"].items():
            cid = str(cid)
            ctype = spec.get("type")
            if ctype not in TYPE_PARTS:
                raise NetlistError(f"{cid}: unknown component type {ctype!r}")
            allowed = TYPE_PARTS[ctype]
            unknown = set(spec) - set(allowed) - PARAM_KEYS - {"type", "label"}
            if unknown:
                raise NetlistError(f"{cid}: unknown keys {sorted(unknown)}")
            comp = Component(
                cid, ctype, str(spec.get("label", cid)), [], {k: spec[k] for k in PARAM_KEYS & set(spec)}
            )
            for key, kind in allowed.items():
                names = spec.get(key, [])
                for name in [names] if isinstance(names, str) else names:
                    name = str(name)
                    ta, sep, tb = name.partition("-")
                    if not sep or not ta or not tb:
                        raise NetlistError(f"{cid}: part {name!r} must be written A-B")
                    resistance = None
                    if kind in LOAD_KINDS:
                        resistance = float(spec.get("resistance", DEFAULT_RESISTANCE[(ctype, kind)]))
                    part = Part(f"{cid}:{name}", cid, name, kind, f"{cid}:{ta}", f"{cid}:{tb}", resistance)
                    if part.id in parts:
                        raise NetlistError(f"duplicate part {part.id}")
                    parts[part.id] = part
                    comp.parts.append(part)
            if ctype in ("contactor", "timer") and not any(p.kind == "coil" for p in comp.parts):
                raise NetlistError(f"{cid}: {ctype} needs a coil")
            components[cid] = comp

        terminals = {t for p in parts.values() for t in (p.a, p.b)}
        nets = {str(k): [str(t) for t in v] for k, v in data["nets"].items()}
        terminal_net: dict[str, str] = {}
        for net, members in nets.items():
            for t in members:
                if t not in terminals:
                    raise NetlistError(f"net {net}: unknown terminal {t}")
                if t in terminal_net:
                    raise NetlistError(f"terminal {t} is in nets {terminal_net[t]} and {net}")
                terminal_net[t] = net
        unconnected = sorted(terminals - set(terminal_net))
        if unconnected:
            raise NetlistError(f"terminals not in any net: {unconnected}")

        supply = data["supply"]
        phases = {str(k): float(v) for k, v in supply["phases"].items()}
        neutral = str(supply["neutral"])
        for s in [*phases, neutral]:
            if s not in nets:
                raise NetlistError(f"supply net {s} is not defined in nets")

        def check_comp(cid: str, ctypes: tuple[str, ...]) -> str:
            if cid not in components or components[cid].type not in ctypes:
                raise NetlistError(f"{cid} must be a component of type {' or '.join(ctypes)}")
            return cid

        power_switch = check_comp(str(data["power_switch"]), ("breaker",))
        protection = [check_comp(str(c), ("fuse", "breaker")) for c in data.get("protection", [])]
        interlocks = [
            (check_comp(str(a), ("contactor",)), check_comp(str(b), ("contactor",)))
            for a, b in data.get("interlocks", [])
        ]

        return cls(
            name=str(data["name"]),
            title=str(data.get("title", data["name"])),
            voltage=float(supply["voltage"]),
            phases=phases,
            neutral=neutral,
            components=components,
            parts=parts,
            nets=nets,
            terminal_net=terminal_net,
            power_switch=power_switch,
            protection=protection,
            interlocks=interlocks,
            layout=data.get("layout", {}),
        )

    def components_of(self, ctype: str) -> list[Component]:
        return [c for c in self.components.values() if c.type == ctype]

    def find_component(self, name: str) -> Component:
        """Look up a component by id ("SB2") or label ("Start Fwd"), case-insensitive."""
        key = name.strip().lower()
        for c in self.components.values():
            if c.id.lower() == key or c.label.lower() == key:
                return c
        raise KeyError(f"unknown component {name!r}")

    def to_text(self) -> str:
        """Plain text netlist for the agent: components, their parts and all nets."""
        kind_names = {
            "breaker_pole": "pole",
            "fuse_pole": "pole",
            "contact_no": "NO",
            "contact_nc": "NC",
            "main": "main NO",
            "delayed_no": "on-delay NO",
            "delayed_nc": "on-delay NC",
            "coil": "coil",
            "lamp": "lamp",
            "heater": "heater",
            "winding": "winding",
        }
        phase_list = ", ".join(self.phases)
        lines = [
            f"Circuit: {self.title}",
            f"Supply: {phase_list} three-phase, neutral {self.neutral}, "
            f"{self.voltage:g} V phase to neutral, {self.voltage * 3**0.5:.0f} V phase to phase.",
            f"Main switch: {self.power_switch}. Mechanical interlocks: "
            + ", ".join(f"{a}/{b}" for a, b in self.interlocks)
            + ".",
            "",
            "Components (id, type, label: parts):",
        ]
        for c in self.components.values():
            groups: dict[str, list[str]] = {}
            for p in c.parts:
                groups.setdefault(kind_names[p.kind], []).append(p.name)
            desc = "; ".join(f"{k} {', '.join(v)}" for k, v in groups.items())
            extra = ""
            if "delay" in c.params:
                extra = f" (delay {c.params['delay']:g} s)"
            lines.append(f"  {c.id} ({c.type}, {c.label}){extra}: {desc}")
        lines += ["", "Nets (net name: connected terminals):"]
        for net, members in self.nets.items():
            lines.append(f"  {net}: {', '.join(members)}")
        return "\n".join(lines)
