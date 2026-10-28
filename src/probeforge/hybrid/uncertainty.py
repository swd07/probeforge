"""Model-uncertainty propagation: does the diagnosis depend on wiring the transcription was unsure of?

The transcription lists uncertain regions (terminal lists). If a terminal of the diagnosed part
(for example KM3:1 or KM3:2 for pole 1-2) lies in such a region, the check builds the alternative wirings of that region: for every
multi-pole part group of a component in the region (main poles, heaters, windings), the terminals
of one side that lie in the region may be connected to each other's nets in any order (this is
what a misread wire crossover does). Each alternative is replayed against every recorded reading
with the diagnosed component's faults of the same mode plus the planner's surviving faults.

If the alternatives that explain all readings give a different pole, the pole is not reported:
the diagnosis keeps the component and failure mode, drops the part, lowers the confidence and says
which region to confirm. If they give a different component, the answer becomes
insufficient_information with the same note. A human (the UI) can confirm which wiring is real;
then the pole that wiring implies is reported. Only the model netlist, the flags and the real
readings are used, never the true netlist.
"""

import copy
import itertools
from collections.abc import Callable

from probeforge.baseline.infogain import Cand, InfoGainBaseline, consistent
from probeforge.faults.catalog import all_faults
from probeforge.hybrid.netlist_io import netlist_dict, to_netlist

MAX_ALTERNATIVES = 216


def _term_net(data: dict) -> dict[str, str]:
    return {str(t): net for net, terms in (data.get("nets") or {}).items() for t in terms}


def regions_for(flags: list[dict], terminals: set[str]) -> list[dict]:
    """The flagged regions that contain one of these terminals."""
    return [f for f in flags if terminals & set(f["terminals"])]


def pin_groups(netlist, region: set[str], components: list[str]) -> list[list[str]]:
    """Terminals that a misread crossover could swap: same side of same-kind parts of one component."""
    groups = []
    for cid in components:
        by_kind: dict[str, list] = {}
        for p in netlist.parts.values():
            if p.component == cid:
                by_kind.setdefault(p.kind, []).append(p)
        for parts in by_kind.values():
            if len(parts) < 2:
                continue
            for side in ("a", "b"):
                ts = [getattr(p, side) for p in parts if getattr(p, side) in region]
                if len(ts) >= 2:
                    groups.append(ts)
    return groups


def alternatives(data: dict, groups: list[list[str]], limit: int = MAX_ALTERNATIVES) -> list[dict]:
    """Netlist dicts with the terminals of each group re-assigned to the group's nets in every order
    (the original wiring and duplicates left out)."""
    tn = _term_net(data)
    seen = {frozenset(frozenset(map(str, v)) for v in data["nets"].values())}
    out = []
    for perms in itertools.product(*(itertools.permutations(g) for g in groups)):
        moved = {}
        for g, perm in zip(groups, perms):
            for t, src in zip(g, perm):
                moved[t] = tn[src]
        nets: dict[str, list[str]] = {}
        for net, terms in data["nets"].items():
            nets.setdefault(net, [])
            for t in terms:
                nets.setdefault(moved.get(str(t), net), []).append(str(t))
        key = frozenset(frozenset(v) for v in nets.values() if v)
        if key in seen:
            continue
        seen.add(key)
        alt = copy.deepcopy(netlist_dict(data))
        alt["nets"] = {k: v for k, v in nets.items() if v}
        out.append(alt)
        if len(out) >= limit:
            break
    return out


def wiring_text(data: dict, terminals: list[str]) -> list[str]:
    """How each region terminal is wired, e.g. 'KM3:1 with KM4:2, M1:W2'."""
    nets = data.get("nets") or {}
    tn = _term_net(data)
    return [f"{t} with {', '.join(x for x in map(str, nets.get(tn.get(t), [])) if x != t) or 'nothing'}"
            for t in terminals if t in tn]


def check(planner: InfoGainBaseline, data: dict, flags: list[dict], draft: dict,
          confirm: Callable[[dict], int | None] | None = None) -> tuple[dict, dict | None]:
    """Returns the (possibly changed) diagnosis args and a log record (None if no flagged region applies)."""
    comp, mode, part = draft.get("component"), draft.get("failure_mode"), draft.get("part")
    if not part:
        return draft, None
    regions = regions_for(flags, {f"{comp}:{t}" for t in str(part).split("-")})
    if not regions:
        return draft, None
    region = sorted({t for f in regions for t in f["terminals"]})
    model = planner.n
    comps = sorted({t.split(":")[0] for t in region if t.split(":")[0] in model.components})
    groups = pin_groups(model, set(region), comps)
    if len(list(itertools.islice(alternatives(data, groups, MAX_ALTERNATIVES + 1), MAX_ALTERNATIVES + 1))) > MAX_ALTERNATIVES:
        groups = pin_groups(model, set(region), [comp])  # too many: only the diagnosed component's pins
    alts = alternatives(data, groups)
    params = sorted({c.params for c in planner.cands}) or [()]
    record = {"component": comp, "region": region, "reasons": [f["reason"] for f in regions],
              "alternatives": len(alts), "consistent_alternatives": 0, "outcomes": {}}
    outcomes: dict[str, list[dict]] = {}  # "KM3:1-2 stuck_open" -> wirings that give it
    for f in planner.faults_left:
        outcomes.setdefault(str(f), []).append(data)
    for alt in alts:
        try:
            n = to_netlist(alt)
        except Exception:  # noqa: BLE001 - an alternative the netlist builder refuses is not a wiring
            continue
        faults = list(dict.fromkeys([*planner.faults_left,
                                     *(f for f in all_faults(n) if f.component == comp and f.mode == mode)]))
        survivors = consistent(n, [Cand(f, p) for f in faults for p in params], planner.history, planner.power0, planner.amps)
        if survivors:
            record["consistent_alternatives"] += 1
        for f in dict.fromkeys(c.fault for c in survivors):
            outcomes.setdefault(str(f), []).append(alt)
    record["outcomes"] = {k: len(v) for k, v in outcomes.items()}
    faults = {k: v for k, v in outcomes.items()}
    same = {k for k in faults if k.split(":")[0].split(" ")[0] == comp and k.endswith(f" {mode}")}
    if set(faults) <= {f"{comp}:{draft['part']} {mode}"}:
        record["verdict"] = "pole holds under every alternative wiring"
        return draft, record
    note = f"confirm wiring at {', '.join(region)}"
    texts = {k: wiring_text(v[0], region) for k, v in sorted(faults.items())}
    differs = [i for i in range(len(region)) if len({tuple(x)[i:i + 1] for x in texts.values()}) > 1]
    options = [{"fault": k, "wiring": [x[i] for i in differs if i < len(x)] or x} for k, x in texts.items()]
    record["options"] = options
    if confirm is not None:
        choice = confirm({"component": comp, "failure_mode": mode, "region": region,
                          "reasons": record["reasons"], "options": options})
        record["human_choice"] = choice
        if choice is not None and 0 <= choice < len(options):
            chosen = options[choice]["fault"]
            target, fmode = chosen.split(" ")
            ccomp, _, part = target.partition(":")
            record["verdict"] = f"human confirmed the wiring that gives {chosen}"
            return {**draft, "component": ccomp, "part": part, "failure_mode": fmode, "confidence": 1.0,
                    "note": f"wiring at {', '.join(region)} confirmed by a human"}, record
    if same == set(faults):
        record["verdict"] = "pole ambiguous"
        return {**draft, "part": "", "confidence": round(1 / len(same), 2),
                "note": f"pole ambiguous ({', '.join(sorted(same))}): {note}"}, record
    record["verdict"] = "component depends on the wiring"
    return {"outcome": "insufficient_information", "confidence": 0.0, "evidence": draft["evidence"],
            "note": f"answer depends on the wiring ({', '.join(sorted(faults))}): {note}"}, record
