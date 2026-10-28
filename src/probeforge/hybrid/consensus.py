"""Self-consistency of several reads of the same schematic.

Muse Spark reads the drawing several times (or several reads already exist). Wherever the reads disagree
about a terminal's connections, that terminal is uncertain, whatever the model said about its own
confidence. The disagreeing terminals are grouped into regions (two of them belong together when they
share a net in any read), which are added to Muse Spark's own flags and so feed the planner's joint
wiring variants. The model netlist is the read that agrees most with the others (connection pairs in
common). Only the reads are compared, never the true netlist.
"""

from itertools import combinations

from probeforge.hybrid.netlist_io import flags_of


def _mates(data: dict) -> dict[str, frozenset]:
    return {str(t): frozenset(map(str, terms)) - {str(t)} for terms in (data.get("nets") or {}).values() for t in terms}


def _pairs(data: dict) -> set[frozenset]:
    return {frozenset(p) for terms in (data.get("nets") or {}).values()
            for p in combinations(sorted(set(map(str, terms))), 2)}


def agreement(a: dict, b: dict) -> float:
    """Share of connection pairs two reads have in common (Jaccard)."""
    pa, pb = _pairs(a), _pairs(b)
    return len(pa & pb) / max(len(pa | pb), 1)


def most_agreeing(reads: list[dict]) -> int:
    """Index of the read with the highest total agreement with the other reads (ties: the earliest)."""
    scores = [sum(agreement(r, o) for j, o in enumerate(reads) if j != i) for i, r in enumerate(reads)]
    return max(range(len(reads)), key=lambda i: (scores[i], -i))


def disagreement_flags(reads: list[dict]) -> list[dict]:
    """Regions where the reads disagree, in the same shape as Muse Spark's flags."""
    mates = [_mates(r) for r in reads]
    terminals = set().union(*mates)
    unsure = {t for t in terminals if len({m.get(t) for m in mates}) > 1}
    # group: two unsure terminals belong together when they share a net in any read
    parent = {t: t for t in unsure}

    def find(t: str) -> str:
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t

    for m in mates:
        for t in unsure:
            for u in m.get(t, ()):
                if u in unsure:
                    parent[find(t)] = find(u)
    groups: dict[str, list[str]] = {}
    for t in sorted(unsure):
        groups.setdefault(find(t), []).append(t)
    return [{"terminals": g, "reason": f"the {len(reads)} reads of the drawing disagree about how these terminals are connected"}
            for g in sorted(groups.values(), key=lambda g: g[0])]


def consensus(reads: list[dict]) -> tuple[dict, list[dict], int]:
    """The model read (its own flags plus every disagreement region) and the index of that read."""
    i = most_agreeing(reads)
    model = dict(reads[i])
    extra = disagreement_flags(reads)
    model["uncertain"] = [*flags_of(reads[i]), *extra]
    return model, extra, i
