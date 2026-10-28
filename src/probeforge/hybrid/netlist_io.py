"""Read step: transcribe the schematic image into our YAML netlist format, and compare netlists.

The model gets the PNG and a format spec with an example of a different, tiny circuit (never the
true YAML). It also lists the regions it is unsure about (wire crossovers, unreadable terminals,
values the drawing does not print) under the top-level key `uncertain`.

The scoring helpers compare a transcription with the true netlist. They are for evaluation and
logging only: nothing they compute is ever sent to the model.
"""

import copy
import re
from itertools import combinations

import yaml

from probeforge.sim.netlist import TYPE_PARTS, Netlist

NON_NETLIST_KEYS = ("uncertain", "layout")

SPEC = """Convert the attached relay-contactor schematic into a YAML netlist in exactly this format.

Top-level keys:
  name: short snake_case id
  title: the drawing title
  supply: {voltage: <phase to neutral volts>, phases: {<phase>: <angle deg>, ...}, neutral: <neutral net name>}
  power_switch: <id of the main breaker>
  protection: [<fuse/breaker ids, the device that should clear a short first comes first>]
  interlocks: [[<contactor id>, <contactor id>], ...]   # mechanical interlock pairs, if any
  components: {<id>: {...}, ...}
  nets: {<net name>: [<COMPONENT:TERMINAL>, ...], ...}

Component types and the keys each may have. Every part is written "A-B" using the two terminal
numbers printed next to it in the drawing:
  breaker:        poles: [list of parts]
  fuse:           poles: [list of parts]
  button:         no_contacts: [...], nc_contacts: [...]
  contactor:      coil: "A-B", main: [main power contacts], no_contacts: [...], nc_contacts: [...]
  timer:          coil: "A-B", no_contacts, nc_contacts, no_delayed: [...], nc_delayed: [...], delay: <s>
  thermal_relay:  heaters: [...], no_contacts: [...], nc_contacts: [...], trip_time: <s>
  lamp:           terminals: "A-B"
  motor:          windings: [...], rated_current: <A>
Every component also has a label (the text written next to it). Optional: resistance (ohms) for a
coil, lamp or winding. Leave out any number that the drawing does not show.

Nets: every terminal of every part must appear in exactly one net. A net is a set of terminals
joined by wires (a dot or a continuous line). Use the wire numbers printed in the drawing as net
names where there are any, otherwise invent a name. Supply phases and the neutral are nets too.
{flags}
Example of the format (a different, tiny circuit, not the one in the image):

```yaml
name: dol_starter
title: Direct on line starter
supply: {voltage: 230, phases: {L1: 0, L2: -120, L3: 120}, neutral: N}
power_switch: Q1
protection: [F1, Q1]
interlocks: []
components:
  Q1: {type: breaker, label: Main switch, poles: ["1-2", "3-4", "5-6"]}
  F1: {type: fuse, label: Control fuse, poles: ["1-2"]}
  K1: {type: contactor, label: Line, coil: A1-A2, main: ["1-2", "3-4", "5-6"], no_contacts: ["13-14"]}
  S1: {type: button, label: Stop, nc_contacts: ["1-2"]}
  S2: {type: button, label: Start, no_contacts: ["3-4"]}
  H1: {type: lamp, label: Run, terminals: X1-X2}
  M1: {type: motor, label: Pump, windings: ["U1-U2", "V1-V2", "W1-W2"]}
nets:
  L1: [Q1:1]
  L2: [Q1:3]
  L3: [Q1:5]
  N: [K1:A2, H1:X2, M1:U2, M1:V2, M1:W2]
  A: [Q1:2, K1:1, F1:1]
  B: [Q1:4, K1:3]
  C: [Q1:6, K1:5]
  U: [K1:2, M1:U1]
  V: [K1:4, M1:V1]
  W: [K1:6, M1:W1]
  "1": [F1:2, S1:1]
  "2": [S1:2, S2:3, K1:13]
  "3": [S2:4, K1:14, K1:A1, H1:X1]{flags_example}
```

Reply with the complete YAML for the circuit in the image inside one ```yaml block."""

FLAGS = """
Uncertain regions: add a top-level key `uncertain` that lists every place you are not sure about,
for example wires that cross (with or without a dot), terminal numbers that are hard to read, or a
value the drawing does not print. Each item gives the terminals involved and a short reason. Use an
empty list only if you are sure of everything.
"""
FLAGS_EXAMPLE = """
uncertain:
  - {terminals: [K1:3, K1:5], reason: "wires cross between K1 and the motor; unsure which pole feeds V"}"""


def spec(flags: bool = True) -> str:
    return SPEC.replace("{flags}", FLAGS if flags else "").replace("{flags_example}", FLAGS_EXAMPLE if flags else "")


def extract_yaml(text: str) -> str:
    m = re.search(r"```(?:yaml)?\s*\n(.*?)```", text or "", re.S)
    return m.group(1) if m else (text or "")


def parse_reply(text: str) -> dict:
    data = yaml.safe_load(extract_yaml(text))
    if not isinstance(data, dict):
        raise ValueError("reply is not a YAML mapping")
    return data


def flags_of(data: dict) -> list[dict]:
    out = []
    for item in data.get("uncertain") or []:
        if isinstance(item, dict):
            out.append({"terminals": [str(t) for t in item.get("terminals") or []], "reason": str(item.get("reason", ""))})
    return out


def netlist_dict(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in NON_NETLIST_KEYS}


def to_netlist(data: dict) -> Netlist:
    return Netlist.from_dict(netlist_dict(data))


def dump(data: dict) -> str:
    """Compact YAML of a netlist dict: one line per component and per net, like the hand-written file."""
    d = netlist_dict(data)
    head = {k: v for k, v in d.items() if k not in ("components", "nets")}
    lines = [yaml.safe_dump(head, default_flow_style=None, sort_keys=False, width=200).rstrip(), "components:"]
    for cid, spec_ in (d.get("components") or {}).items():
        lines.append(f"  {cid}: " + yaml.safe_dump(spec_, default_flow_style=True, sort_keys=False, width=400).strip())
    lines.append("nets:")
    for net, terms in (d.get("nets") or {}).items():
        lines.append(f"  {yaml.safe_dump(str(net)).splitlines()[0]}: [{', '.join(map(str, terms))}]")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ comparison

def net_sets(data_or_netlist) -> dict[frozenset, str]:
    nets = data_or_netlist.nets if isinstance(data_or_netlist, Netlist) else (data_or_netlist.get("nets") or {})
    return {frozenset(map(str, v or [])): str(k) for k, v in nets.items()}


def netlist_diff(old: dict, new: dict) -> list[str]:
    """Human-readable diff: components whose spec changed, nets (compared as terminal sets, so a
    rename alone is not a change) and other top-level keys."""
    lines = []
    oc, nc = old.get("components") or {}, new.get("components") or {}
    flow = lambda v: yaml.safe_dump(v, default_flow_style=True, sort_keys=False, width=400).strip()  # noqa: E731
    for cid in list(oc) + [c for c in nc if c not in oc]:
        if oc.get(cid) != nc.get(cid):
            if cid in oc:
                lines.append(f"- {cid}: {flow(oc[cid])}")
            if cid in nc:
                lines.append(f"+ {cid}: {flow(nc[cid])}")
    on, nn = net_sets(old), net_sets(new)
    for s, name in on.items():
        if s not in nn:
            lines.append(f"- net {name}: [{', '.join(sorted(s))}]")
    for s, name in nn.items():
        if s not in on:
            lines.append(f"+ net {name}: [{', '.join(sorted(s))}]")
    for key in ("supply", "power_switch", "protection", "interlocks"):
        if old.get(key) != new.get(key):
            lines.append(f"- {key}: {flow(old.get(key))}")
            lines.append(f"+ {key}: {flow(new.get(key))}")
    return lines


def wrong_nets(data: dict, true: Netlist) -> list[list[str]]:
    """True nets that the netlist does not reproduce exactly (as terminal sets)."""
    found = net_sets(data)
    return [sorted(v) for v in true.nets.values() if frozenset(v) not in found]


def param_values(data: dict) -> dict[str, float]:
    out = {}
    for cid, s in (data.get("components") or {}).items():
        if isinstance(s, dict):
            for k in ("delay", "trip_time", "rated_current"):
                if k in s:
                    out[f"{cid}.{k}"] = s[k]
    return out


def _pairs(nets: dict) -> set[frozenset]:
    return {frozenset(p) for ts in nets.values() for p in combinations(sorted(set(map(str, ts or []))), 2)}


def _prf(found: set, true: set) -> dict:
    tp = len(found & true)
    return {"found": len(found), "true": len(true), "matched": tp,
            "precision": round(tp / len(found), 3) if found else 0.0, "recall": round(tp / len(true), 3) if true else 0.0}


def _part_set(cs: dict) -> set[tuple]:
    out = set()
    for cid, s in cs.items():
        if not isinstance(s, dict):
            continue
        for key in TYPE_PARTS.get(s.get("type"), {}):
            names = s.get(key, [])
            for name in [names] if isinstance(names, str) else names or []:
                out.add((str(cid), str(name), key))
    return out


def structure(data: dict, true_data: dict, true: Netlist) -> dict:
    comps = data.get("components") or {}
    true_comps = true_data["components"]
    parts_found, parts_true = _part_set(comps), _part_set(true_comps)
    terms = lambda ps: {f"{c}:{t}" for c, n, _ in ps for t in n.split("-", 1)}  # noqa: E731
    wrong = wrong_nets(data, true)
    return {
        "components": _prf(set(map(str, comps)), set(true_comps)),
        "component_types_right": sum(isinstance(comps.get(c), dict) and comps[c].get("type") == s["type"]
                                     for c, s in true_comps.items()),
        "parts": _prf(parts_found, parts_true),
        "parts_missing": sorted(f"{c}:{n} ({k})" for c, n, k in parts_true - parts_found),
        "parts_extra": sorted(f"{c}:{n} ({k})" for c, n, k in parts_found - parts_true),
        "terminals": _prf(terms(parts_found), terms(parts_true)),
        "connections": _prf(_pairs(data.get("nets") or {}), _pairs(true.nets)),
        "nets_exact": {"matched": len(true.nets) - len(wrong), "true": len(true.nets)},
        "nets_wrong": wrong,
        "interlocks_right": sorted(map(sorted, data.get("interlocks") or [])) == sorted(map(sorted, true_data["interlocks"])),
    }


def score_flags(flags: list[dict], data: dict, true: Netlist) -> dict:
    """Do the uncertain regions point at the nets that are actually wrong?"""
    wrong = wrong_nets(data, true)
    wrong_terms = {t for net in wrong for t in net}
    hits = [f for f in flags if wrong_terms & set(f["terminals"])]
    covered = [net for net in wrong if any(set(net) & set(f["terminals"]) for f in flags)]
    return {"flags": len(flags), "flags_on_wrong_nets": len(hits), "wrong_nets": len(wrong),
            "wrong_nets_flagged": len(covered)}


# ------------------------------------------------------------------ behaviour check

# healthy operating sequence: (label, action)
SEQUENCE = [
    ("power on", lambda c: c.set_power(True)),
    ("Start Fwd pressed", lambda c: c.press("SB2")),
    ("1 s later (star)", lambda c: c.step(1.0)),
    ("6 s later (delta)", lambda c: c.step(6.0)),
    ("Start Rev pressed while forward runs", lambda c: c.press("SB3")),
    ("Stop pressed", lambda c: (c.press("SB1"), c.step(0.5))),
    ("Start Rev pressed", lambda c: c.press("SB3")),
    ("6 s later (reverse delta)", lambda c: c.step(6.0)),
    ("Stop pressed", lambda c: (c.press("SB1"), c.step(0.5))),
]


def fill_params(data: dict, true_data: dict) -> list[str]:
    """Copy parameters the drawing does not print from the true file (behaviour check only)."""
    filled = []
    for cid, s in (data.get("components") or {}).items():
        t = true_data["components"].get(cid)
        if not (isinstance(s, dict) and t):
            continue
        for k in ("delay", "trip_time", "rated_current"):
            if k in t and k not in s:
                s[k] = t[k]
                filled.append(f"{cid}.{k}")
    return filled


def _trace(c, terminals: list[str]) -> list[dict]:
    out = []
    for label, act in SEQUENCE:
        act(c)
        ind = c.indicators()
        volts = {}
        for t in terminals:
            try:
                volts[t] = round(c.voltage(t, c.netlist.neutral))
            except KeyError:
                volts[t] = None
        out.append({"step": label, "lamps": ind["lamps"], "motor": ind["motor"], "volts": volts})
    return out


def behaviour(data: dict, true: Netlist, true_data: dict | None = None) -> dict:
    """Drive the healthy sequence on the netlist and on the true circuit; compare panel and volts to N.
    With true_data, unprinted parameters are copied from it first (so this checks wiring)."""
    from probeforge.sim import Circuit

    data = copy.deepcopy(data)
    filled = fill_params(data, true_data) if true_data else []
    try:
        n = to_netlist(data)
    except Exception as e:  # noqa: BLE001 - any validation failure is the result
        return {"loads": False, "error": f"{type(e).__name__}: {e}"}
    terminals = sorted(true.terminal_net)
    try:
        got = _trace(Circuit(n), terminals)
    except Exception as e:  # noqa: BLE001
        return {"loads": True, "runs": False, "error": f"{type(e).__name__}: {e}"}
    want = _trace(Circuit(true), terminals)
    steps, v_ok, v_all = [], 0, 0
    for g, w in zip(got, want):
        same = g["lamps"] == w["lamps"] and g["motor"] == w["motor"]
        bad_v = [t for t in terminals if g["volts"][t] != w["volts"][t]]
        v_ok += len(terminals) - len(bad_v)
        v_all += len(terminals)
        steps.append({"step": w["step"], "panel_same": same, "motor": g["motor"], "true_motor": w["motor"],
                      "lamps": g["lamps"], "true_lamps": w["lamps"], "voltage_mismatches": bad_v})
    return {"loads": True, "runs": True, "params_filled_from_truth": filled,
            "panel_steps_same": sum(s["panel_same"] for s in steps), "steps": len(steps),
            "voltages_same": round(v_ok / v_all, 3), "sequence": steps}
