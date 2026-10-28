"""Model uncertainty: alternative wirings of the regions the transcription flagged, and what they mean for
the diagnosis.

The transcription lists uncertain regions (terminal lists). An alternative wiring of a region lets the
terminals on one side of same-kind parts of a component (main poles, heaters, windings, aux contacts)
lie in each other's nets, in any order: that is what a misread wire crossover does. These variants feed
the planner's joint hypotheses (fault x wiring, see baseline/infogain.py): the planner adds the ones
that reproduce every reading and keeps measuring until the answer no longer depends on them.

check() then turns the planner's final joint candidates into the reported answer: one fault left, it
stands; several poles of one component, the pole is dropped ("pole ambiguous: confirm wiring at ...")
with lower confidence; different components, insufficient_information with the same note. A human (the
UI) can say which wiring the panel really has, and the fault that wiring implies is reported. Only the
model netlist, the flags and the real readings are used, never the true netlist.
"""

import copy
import itertools
from collections.abc import Callable

from probeforge.baseline.infogain import InfoGainBaseline, Variant
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


def _variants(data: dict, groups: list[list[str]], comps: tuple, region: tuple, label: str) -> list[Variant]:
    out = []
    for alt in alternatives(data, groups):
        try:
            out.append(Variant(label, comps, to_netlist(alt), region, alt))
        except Exception:  # noqa: BLE001 - an alternative the netlist builder refuses is not a wiring
            continue
    return out


def variant_source(get_data: Callable[[], dict], flags: list[dict]) -> Callable[[set | None], list[Variant]]:
    """For the planner. terminals given: the regions containing them, all their components' pins at once
    (only the components that own one of the terminals if that is too many). None: every flagged region,
    one component's pins at a time."""

    def source(terminals: set | None) -> list[Variant]:
        data = get_data()
        model = to_netlist(data)
        out: list[Variant] = []
        if terminals is None:
            for i, f in enumerate(flags):
                region = set(f["terminals"])
                for comp in sorted({t.split(":")[0] for t in region if t.split(":")[0] in model.components}):
                    groups = pin_groups(model, region, [comp])
                    if groups:
                        out += _variants(data, groups, (comp,), tuple(sorted(region)), f"region {i + 1}, {comp} pins")
            return out
        regions = regions_for(flags, terminals)
        region = {t for f in regions for t in f["terminals"]}
        if not region:
            return []
        comps = sorted({t.split(":")[0] for t in region if t.split(":")[0] in model.components})
        groups = pin_groups(model, region, comps)
        if len(alternatives(data, groups, MAX_ALTERNATIVES + 1)) > MAX_ALTERNATIVES:
            comps = sorted({t.split(":")[0] for t in terminals})
            groups = pin_groups(model, region, comps)
        return _variants(data, groups, tuple(comps), tuple(sorted(region)), "around " + ", ".join(sorted(terminals)))

    return source


def wiring_text(data: dict, terminals: list[str]) -> list[str]:
    """How each region terminal is wired, e.g. 'KM3:1 with KM4:2, M1:W2'."""
    nets = data.get("nets") or {}
    tn = _term_net(data)
    return [f"{t} with {', '.join(x for x in map(str, nets.get(tn.get(t), [])) if x != t) or 'nothing'}"
            for t in terminals if t in tn]


def check(planner: InfoGainBaseline, data: dict, flags: list[dict], draft: dict,
          confirm: Callable[[dict], int | None] | None = None) -> tuple[dict, dict | None]:
    """Returns the (possibly changed) diagnosis args and a log record (None if no wiring variant was involved)."""
    if not planner.joint or not planner.wiring_region:
        return draft, None
    region = sorted(planner.wiring_region)
    by_fault: dict[str, list[int]] = {}
    for c in planner.cands:
        by_fault.setdefault(str(c.fault), []).append(c.variant)
    record = {"component": draft.get("component"), "region": region, "alternatives": len(planner.models) - 1,
              "consistent_alternatives": len({c.variant for c in planner.cands if c.variant}),
              "outcomes": {k: len(set(v)) for k, v in by_fault.items()}}
    if len(by_fault) <= 1:
        record["verdict"] = "pole holds under every wiring that fits the readings"
        return draft, record

    def wiring_of(vid: int) -> dict:
        return data if vid == 0 else planner.variants[vid].data

    texts = {k: wiring_text(wiring_of(v[0]), region) for k, v in sorted(by_fault.items())}
    differs = [i for i in range(len(region)) if len({tuple(x)[i:i + 1] for x in texts.values()}) > 1]
    options = [{"fault": k, "wiring": [x[i] for i in differs if i < len(x)] or x} for k, x in texts.items()]
    record["options"] = options
    note = f"confirm wiring at {', '.join(region)}"
    evidence = draft.get("evidence") or planner.evidence[-6:]
    if confirm is not None:
        choice = confirm({"component": draft.get("component"), "failure_mode": draft.get("failure_mode"),
                          "region": region, "reasons": [f["reason"] for f in regions_for(flags, set(region))],
                          "options": options})
        record["human_choice"] = choice
        if choice is not None and 0 <= choice < len(options):
            chosen = options[choice]["fault"]
            target, fmode = chosen.split(" ")
            ccomp, _, part = target.partition(":")
            record["verdict"] = f"human confirmed the wiring that gives {chosen}"
            return {"outcome": "diagnosed", "component": ccomp, "part": part, "failure_mode": fmode, "confidence": 1.0,
                    "evidence": evidence, "note": f"wiring at {', '.join(region)} confirmed by a human"}, record
    kinds = {k.split(":")[0].split(" ")[0] + " " + k.split(" ")[-1] for k in by_fault}
    if draft.get("outcome") == "diagnosed" and len(kinds) == 1:
        record["verdict"] = "pole ambiguous"
        return {**draft, "part": "", "confidence": round(1 / len(by_fault), 2),
                "note": f"pole ambiguous ({', '.join(sorted(by_fault))}): {note}"}, record
    record["verdict"] = "component depends on the wiring"
    return {"outcome": "insufficient_information", "confidence": 0.0, "evidence": evidence,
            "note": f"answer depends on the wiring ({', '.join(sorted(by_fault))}): {note}"}, record
