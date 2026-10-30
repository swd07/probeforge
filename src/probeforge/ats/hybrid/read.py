"""Hybrid v2, Read step on the ATS bench: Muse Spark transcribes drawing sheets of the transfer switch into a compact
description (devices with their contacts, the harness wire run list, unnumbered joints); code builds our netlist from it.

The model reads the drawing; the naming conventions of our netlist (harness wire part ids, plug / jack pins, net names)
are applied by `build`, so they never have to be guessed. The images are crops of the drawing sheets only (see
scripts/render_ats_sheets.py for the privacy rule). The spec's example is a different, made-up circuit, never the true
netlist. Several reads are compared with the relay-panel consensus (hybrid/consensus.py, unchanged): terminals whose
connections the reads disagree about become uncertain regions.
"""

import base64
import re
import time
from pathlib import Path

import yaml

from probeforge.agent.loop import _cost
from probeforge.hybrid.consensus import consensus
from probeforge.hybrid.llm import EM_DASH, Usage
from probeforge.hybrid.netlist_io import flags_of
from probeforge.sim.netlist import Netlist

ROOT = Path(__file__).resolve().parents[4]
SHEET_DIR = ROOT / "docs" / "vendor" / "crops"
SHEETS = ["s3_power.png", "s3_operator.png", "s3_table.png", "s4_sensing.png", "s4_position.png", "s2_engine.png",
          "s6_wires.png"]

SPEC = """The attached images are drawing sheets of one automatic transfer switch wiring diagram: the main power poles, the
transfer switch (TS) operator circuit, the TS control contact table, the source and load sensing circuits with the TS
position contacts (also enlarged on their own), the engine starting signals, and the main harness wire run listing. Transcribe them into YAML in
exactly this format (keys and meaning below; the example at the end is a different, made-up switch).

title: the drawing title
normal_source: {A: <terminal>, B: <terminal>, C: <terminal>}   # where the Normal source phases enter (line side of the Normal breaker)
emergency_source: {A: <terminal>, B: <terminal>, C: <terminal>}   # where the Emergency source phases land on the TS
neutrals: {normal: <terminal>, emergency: <terminal>, load: <terminal>}
load: {A: <terminal>, B: <terminal>, C: <terminal>}
breaker: {id: <id>, label: <label>, poles: ["<line>-<load>", ...]}   # the Normal source breaker, if drawn
transfer_switch:            # the TS, every part written "X-Y" with the two TS terminal numbers or names printed next to it
  main_normal: [...]        # main power contacts closed on Normal (including a switched neutral pole if drawn)
  main_emergency: [...]     # main power contacts closed on Emergency
  control_closed_normal: [...]      # TS control (cut-off) contacts closed on Normal (from the TS control contact table)
  control_closed_emergency: [...]   # TS control (cut-off) contacts closed on Emergency
  aux_closed_normal: [...]          # auxiliary contacts closed on Normal that are wired in the drawing (feature 14A)
  aux_closed_emergency: [...]       # auxiliary contacts closed on Emergency that are wired in the drawing (feature 14B)
  solenoid: "<terminal>-<terminal>"
relays:                     # relay contacts inside the controller, terminals written with the controller jack numbers
  <relay id>: {no: ["J<n>-J<m>", ...], nc: [...]}   # name a junction between two relay contacts that has no jack
                                                    # number X1, X2, ...: the same X name on two contacts means joined
controller_inputs: [J<n>, ...]   # controller jack pins used as sensing inputs (source and load voltage, TS position)
terminal_block: {id: <id>, label: <label>, points: [<n>, ...]}   # field terminal block (engine starting signals)
wires:                      # every numbered wire of the main harness wire run listing, in the order listed:
  - [<number>, <end>, <end>]   # ends exactly as printed, e.g. TS-6, P-3, TB/TS-14
joints:                     # connections drawn without a harness wire number, e.g. a breaker load terminal to a TS
  - [<terminal>, <terminal>]   # main terminal. Terminals: <device id>:<terminal>, e.g. TS:4, 52N:2
uncertain:                  # every place you are not sure about (hard to read numbers, unclear connections)
  - {terminals: [<terminal>, ...], reason: <short reason>}

Reading conventions:
- Main power contacts: write them with the TS terminal numbers printed at their ends (for example "TS -1" next to a
  source tag), not with the source or load names. If no Normal breaker is drawn, leave `breaker` out and give the
  Normal source phases at the TS terminals.
- Controller connections are drawn as plug / jack symbols with a number next to "CP J": that number n is controller
  jack J<n>, which mates with harness plug pin P<n>. Dashed Px / Jx symbols belong to an optional extension harness:
  ignore them (plug P mates directly with jack J).
- A contact side with no number of its own that is joined by a line to a numbered terminal takes that terminal's
  number (for example several contacts sharing one common terminal).
- Copy wire numbers exactly as printed in the wire run listing, even when a number appears twice.
- Never leave a part out because its numbers are hard to read: write your best reading and list it under `uncertain`.
- Only include what the drawing shows as wired on this switch; leave out optional accessories drawn as not wired.

Example of the format (a different, made-up switch):

```yaml
title: Two source transfer panel
normal_source: {A: 52N:1, B: 52N:3, C: 52N:5}
emergency_source: {A: TS:41, B: TS:42, C: TS:43}
neutrals: {normal: TS:N1, emergency: TS:N2, load: TS:N3}
load: {A: TS:51, B: TS:52, C: TS:53}
breaker: {id: 52N, label: Normal breaker, poles: ["1-2", "3-4", "5-6"]}
transfer_switch:
  main_normal: ["31-51", "32-52", "33-53"]
  main_emergency: ["41-51", "42-52", "43-53"]
  control_closed_normal: ["60-61"]
  control_closed_emergency: ["62-63"]
  aux_closed_normal: ["80-81"]
  aux_closed_emergency: ["80-82"]
  solenoid: "C1-C2"
relays:
  RN: {no: ["J5-J6"], nc: ["X1-J6"]}
  RE: {no: ["J7-X1"]}
controller_inputs: [J10, J11, J12]
terminal_block: {id: TB, label: Field terminals, points: [1, 2]}
wires:
  - [1, TS-60, P-5]
  - [2, TS-C1, P-6]
  - [3, TS-80, P-10]
  - [4, TS-81, P-11]
  - [5, TB-1, P-12]
joints:
  - [52N:2, TS:31]
uncertain:
  - {terminals: [TS:62, TS:63], reason: "contact numbers hard to read in the table"}
```

Reply with the complete YAML inside one ```yaml block."""

TS_KEYS = {"main_normal": "main_normal", "main_emergency": "main_emergency", "control_closed_normal": "cutoff_normal",
           "control_closed_emergency": "cutoff_emergency", "aux_closed_normal": "aux_normal",
           "aux_closed_emergency": "aux_emergency"}


# ------------------------------------------------------------------ model call


def sheet_images() -> list[bytes]:
    missing = [s for s in SHEETS if not (SHEET_DIR / s).exists()]
    if missing:
        raise FileNotFoundError(f"render the drawing sheets first (scripts/render_ats_sheets.py): {missing}")
    return [(SHEET_DIR / s).read_bytes() for s in SHEETS]


def chat_images(client, usage: Usage, purpose: str, text: str, images: list[bytes], effort: str = "medium") -> str:
    """One Muse Spark call with several drawing images (PNG); usage and latency are recorded like hybrid/llm.chat."""
    content = [{"type": "text", "text": text}] + [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}} for png in images]
    t0 = time.perf_counter()
    resp = client.chat.completions.create(model=usage.model, messages=[{"role": "user", "content": content}],
                                          reasoning_effort=effort)
    record(usage, purpose, effort, resp, time.perf_counter() - t0)
    return (resp.choices[0].message.content or "").replace(EM_DASH, ", ")


def record(usage: Usage, purpose: str, effort: str, resp, latency: float) -> None:
    """Tokens and cost of one call into usage (the same fields as hybrid/llm.chat records)."""
    u = resp.usage
    prompt = u.prompt_tokens if u else 0
    completion = u.completion_tokens if u else 0
    details = getattr(u, "prompt_tokens_details", None) if u else None
    cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
    cost = _cost(usage.model, prompt, cached, completion)
    usage.turns += 1
    usage.prompt_tokens += prompt
    usage.cached_tokens += cached
    usage.completion_tokens += completion
    usage.cost_usd += cost
    usage.turn_log.append({"turn": usage.turns, "purpose": purpose, "effort": effort, "prompt_tokens": prompt,
                           "cached_tokens": cached, "completion_tokens": completion, "cost_usd": round(cost, 5),
                           "latency_s": round(latency, 1),
                           "text": (resp.choices[0].message.content or "").replace(EM_DASH, ", ")})


def parse_reply(text: str) -> dict:
    m = re.search(r"```(?:yaml)?\s*\n(.*?)```", text or "", re.S)
    data = yaml.safe_load(m.group(1) if m else (text or ""))
    if not isinstance(data, dict):
        raise ValueError("reply is not a YAML mapping")
    return data


# ------------------------------------------------------------------ build


def _end(e: str) -> tuple[str, str]:
    """A wire end as printed (TS-6, P-3, TB/TS-14) -> (terminal id, short label for the wire part id)."""
    s = str(e).strip().replace(" ", "").upper()
    m = re.fullmatch(r"(TB/TS|TB|TS|P|J)-?([A-Z0-9]+)", s)
    if not m:
        raise ValueError(f"unreadable wire end {e!r}")
    dev, t = m.groups()
    if dev in ("TB/TS", "TB"):
        return f"TBTS:{t}", f"TB{t}"
    if dev == "P":
        return f"XP:P{t}", f"P{t}"
    if dev == "J":
        return f"XP:J{t}", f"J{t}"
    return f"TS:{t}", f"TS{t}"


def _term(t) -> str:
    s = str(t).strip()
    if ":" not in s:
        if re.fullmatch(r"(TB/TS|TB|TS|P|J)-[A-Z0-9]+", s.upper()):
            return _end(s)[0]
        s = f"TS:{s}"  # a bare terminal name (NA, LA, 4) is read as a TS terminal
    dev, name = s.split(":", 1)
    dev = dev.strip().upper()
    return f"{'TBTS' if dev in ('TB', 'TB/TS') else dev}:{name.strip().upper()}"


def build(t: dict) -> dict:
    """Our netlist dict from a compact transcription (raises ValueError if it cannot be built)."""
    comps: dict = {}
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def join(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    terminals: set[str] = set()

    def add(cid: str, a: str, b: str | None = None) -> None:
        terminals.add(f"{cid}:{a}")
        if b is not None:
            terminals.add(f"{cid}:{b}")

    br = t.get("breaker") or {}
    if not br:  # the drawing sheets do not show the Normal source breaker: a stand-in so the source can be isolated
        ns = t.get("normal_source") or {}
        br = {"id": "NSD", "label": "Normal source disconnect (not on the drawing sheets, added by the builder)",
              "poles": ["1-2", "3-4", "5-6"]}
        t = {**t, "normal_source": {"A": "NSD:1", "B": "NSD:3", "C": "NSD:5"},
             "joints": [*(t.get("joints") or []), *([f"NSD:{2 * i + 2}", ns[k]] for i, k in enumerate("ABC") if ns.get(k))]}
    if br:
        bid = str(br["id"]).upper()
        poles = [str(p).upper() for p in br.get("poles") or []]
        comps[bid] = {"type": "breaker", "label": str(br.get("label") or bid), "poles": poles}
        for p in poles:
            add(bid, *p.split("-", 1))
    ts = t.get("transfer_switch") or {}
    spec = {"type": "transfer_switch", "label": "Transfer switch"}
    for key, ours in TS_KEYS.items():
        parts = [str(p).upper() for p in ts.get(key) or []]
        spec[ours] = parts
        for p in parts:
            add("TS", *p.split("-", 1))
    sol = str(ts.get("solenoid") or "A-B").upper()
    spec["solenoid"] = [sol]
    add("TS", *sol.split("-", 1))
    comps["TS"] = spec
    pins: set[int] = set()
    for rid, r in (t.get("relays") or {}).items():
        rid = str(rid).upper()
        r = r or {}
        no = [str(p).upper() for p in r.get("no", r.get(False)) or []]  # YAML 1.1 reads the key `no` as false
        nc = [str(p).upper() for p in r.get("nc") or []]
        comps[rid] = {"type": "relay", "label": f"{rid} relay (in controller)", "no_contacts": no, "nc_contacts": nc}
        for p in no + nc:
            a, b = p.split("-", 1)
            add(rid, a, b)
            for x in (a, b):
                if x.startswith("J"):
                    pins.add(int(x[1:]))
                    join(f"{rid}:{x}", f"XP:{x}")
                elif x.startswith("X"):
                    join(f"{rid}:{x}", f"CP{x}")  # a junction inside the controller
    inputs = [str(j).upper() for j in t.get("controller_inputs") or []]
    if inputs:
        comps["CP"] = {"type": "controller", "label": "Controller", "inputs": inputs}
        for j in inputs:
            add("CP", j)
            pins.add(int(j[1:]))
            join(f"CP:{j}", f"XP:{j}")
    tb = t.get("terminal_block") or {}
    if tb:
        pts = [str(p).upper() for p in tb.get("points") or []]
        comps["TBTS"] = {"type": "terminal_block", "label": str(tb.get("label") or "TB/TS"), "points": pts}
        for p in pts:
            add("TBTS", p)
    wires, seen = [], {}
    for w in t.get("wires") or []:
        num, ea, eb = str(w[0]).upper(), w[1], w[2]
        (ta, la), (tb_, lb) = _end(ea), _end(eb)
        seen[num] = seen.get(num, 0) + 1
        dup = sum(1 for x in t.get("wires") or [] if str(x[0]).upper() == num) > 1
        wid = f"W{num}{'AB'[seen[num] - 1] if dup else ''}"
        name = f"{wid}_{la}-{wid}_{lb}"
        wires.append(name)
        add("H1", f"{wid}_{la}", f"{wid}_{lb}")
        join(f"H1:{wid}_{la}", ta)
        join(f"H1:{wid}_{lb}", tb_)
        for term in (ta, tb_):
            if term.startswith("XP:P"):
                pins.add(int(term[4:]))
            terminals.add(term)
    if wires:
        comps["H1"] = {"type": "harness", "label": "Harness", "wires": wires}
    if pins:
        comps["XP"] = {"type": "connector", "label": "Plug P / jack J", "pins": [f"P{n}-J{n}" for n in sorted(pins)]}
        for n in sorted(pins):
            add("XP", f"P{n}", f"J{n}")
    for a, b in t.get("joints") or []:
        join(_term(a), _term(b))
        terminals.update((_term(a), _term(b)))
    names = {}
    for ph, key in zip("ABC", ("A", "B", "C")):
        names[_term((t.get("normal_source") or {})[key])] = f"U{ph}"
        names[_term((t.get("emergency_source") or {})[key])] = f"E{ph}"
        names[_term((t.get("load") or {})[key])] = f"L{ph}"
    neu = t.get("neutrals") or {}
    for key, net in (("normal", "NN"), ("emergency", "EN"), ("load", "LN")):
        if neu.get(key):
            names[_term(neu[key])] = net
    part_terms = {f"{cid}:{x}" for cid, s in comps.items() for k, v in s.items() if isinstance(v, list)
                  for p in v for x in str(p).split("-", 1)}
    unattached = sorted(terminals - part_terms)  # named in the wiring but on no part: left out of the nets, logged
    terminals &= part_terms
    for term in terminals:
        find(term)
    groups: dict[str, list[str]] = {}
    for term in sorted(terminals):
        groups.setdefault(find(term), []).append(term)
    # a name given to an unattached terminal (e.g. a neutral drawn unswitched) goes to the net it was joined to
    for term in unattached:
        if term in names:
            root = find(term)
            if root in groups:
                names.setdefault(groups[root][0], names[term])
    nets: dict[str, list[str]] = {}
    for members in groups.values():
        named = [names[m] for m in members if m in names]
        if named:
            net = named[0]
        elif any(m.startswith("TBTS:") for m in members):
            net = "TB" + next(m for m in members if m.startswith("TBTS:")).split(":")[1]
        else:
            ts_t = next((m for m in members if m.startswith("TS:")), None)
            pin = next((m for m in members if m.startswith("XP:")), None)
            cpx = next((m for m in members if m.split(":")[1].startswith("X")), None)
            net = ("TS" + ts_t.split(":")[1]) if ts_t else (pin.split(":")[1] if pin else (
                "CP" + cpx.split(":")[1] if cpx else members[0].replace(":", "_")))
        while net in nets:
            net += "'"
        nets[net] = members
    for req in ("UA", "UB", "UC", "EA", "EB", "EC", "NN", "EN"):
        if req not in nets:
            raise ValueError(f"net {req} missing: give the source phases and neutrals")
    start = [n for n in nets if n in ("TB14", "TB15")]
    data = {
        "name": "ats_transcription",
        "title": str(t.get("title") or "transcribed transfer switch"),
        "supply": {"voltage": 120, "phases": {"UA": 0, "UB": -120, "UC": 120}, "neutral": "NN"},
        "alternate_supply": {"label": "Emergency source", "voltage": 120, "phases": {"EA": 0, "EB": -120, "EC": 120},
                             "neutral": "EN", **({"start_contact": start} if len(start) == 2 else {})},
        "power_switch": next((c for c, s in comps.items() if s["type"] == "breaker"), None),
        "protection": [c for c, s in comps.items() if s["type"] == "breaker"],
        "components": comps,
        "nets": nets,
        "unattached_terminals": unattached,
        "uncertain": [{"terminals": [_term(x) if ":" in str(x) else str(x) for x in f.get("terminals") or []],
                       "reason": str(f.get("reason", ""))} for f in t.get("uncertain") or [] if isinstance(f, dict)],
    }
    if data["power_switch"] is None:
        del data["power_switch"]
    return data


def to_netlist(data: dict) -> Netlist:
    return Netlist.from_dict({k: v for k, v in data.items() if k not in ("uncertain", "layout", "unattached_terminals")})


def read_once(client, usage: Usage, images: list[bytes], effort: str = "medium", purpose: str = "transcription",
              keep: list | None = None) -> tuple[dict, dict]:
    """One read; the raw reply text goes into keep (if given) before anything can fail."""
    reply = chat_images(client, usage, purpose, SPEC, images, effort)
    if keep is not None:
        keep.append(reply)
    raw = parse_reply(reply)
    data = build(raw)
    to_netlist(data)
    return raw, data


def read_consensus(client, usage: Usage, images: list[bytes] | None = None, reads: int = 3,
                   effort: str = "medium") -> tuple[dict, list[dict], dict, list[dict]]:
    """Several reads; returns the model netlist dict (its own flags plus disagreement regions), all flags, a summary,
    and the raw compact transcriptions (for the log)."""
    images = images or sheet_images()
    usable, raws, errors, replies = [], [], [], []
    for i in range(reads):
        try:
            raw, data = read_once(client, usage, images, effort, f"transcription {i + 1}/{reads}", replies)
            usable.append(data)
            raws.append(raw)
        except Exception as e:  # noqa: BLE001 - an unusable read is left out of the vote
            errors.append(f"read {i + 1}: {type(e).__name__}: {e}")
    if not usable:
        raise ValueError("no usable drawing read: " + "; ".join(errors))
    if len(usable) == 1:
        return usable[0], flags_of(usable[0]), {"reads": 1, "model_read": 1, "disagreement_regions": 0, "errors": errors}, raws
    model, extra, i = consensus(usable)
    return model, flags_of(model), {"reads": len(usable), "model_read": i + 1, "disagreement_regions": len(extra),
                                    "errors": errors}, raws
