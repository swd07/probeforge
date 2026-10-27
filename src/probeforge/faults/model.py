"""Fault definition and the failure modes each kind of part can have."""

from dataclasses import dataclass

# Failure modes of a single two-terminal part, by part kind.
PART_MODES: dict[str, tuple[str, ...]] = {
    "breaker_pole": ("open",),
    "fuse_pole": ("open",),
    "contact_no": ("stuck_open", "stuck_closed"),
    "contact_nc": ("stuck_open", "stuck_closed"),
    "main": ("stuck_open", "stuck_closed"),
    "delayed_no": ("stuck_open", "stuck_closed"),
    "delayed_nc": ("stuck_open", "stuck_closed"),
    "coil": ("open", "short"),
    "lamp": ("open",),
    "heater": ("open",),
    "winding": ("open",),
}

# Failure modes of a whole device, by component type.
#   welded:  contactor armature held closed (main contacts welded), so every
#            contact of it stays in the actuated position, aux NC included
#   tripped: thermal overload relay tripped
#   stuck:   timer coil works but the timing element never switches
COMPONENT_MODES: dict[str, tuple[str, ...]] = {
    "contactor": ("welded",),
    "thermal_relay": ("tripped",),
    "timer": ("stuck",),
}


@dataclass(frozen=True)
class Fault:
    component: str
    mode: str
    part: str | None = None  # e.g. "13-14"; None for a whole-device fault

    @property
    def target(self) -> str:
        return f"{self.component}:{self.part}" if self.part else self.component

    def __str__(self) -> str:
        return f"{self.target} {self.mode}"

    def to_dict(self) -> dict:
        d = {"component": self.component, "mode": self.mode}
        if self.part:
            d["part"] = self.part
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Fault":
        part = d.get("part")
        return cls(component=str(d["component"]), mode=str(d["mode"]), part=str(part) if part else None)
