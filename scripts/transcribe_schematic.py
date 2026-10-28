"""Test B: can Muse Spark transcribe the schematic image into our YAML netlist format?

Usage:  uv run python scripts/transcribe_schematic.py [--runs 3] [--effort medium]

The model gets the same PNG the agent sees and a format spec (keys, part kinds, an example of a
different, tiny circuit), never the true YAML. Each transcription is scored against the true file:

- components: ids found (and whether the type matches)
- parts: COMPONENT:A-B with their kind (NO, NC, coil, ...)
- terminals: COMPONENT:TERMINAL
- connections: pairs of terminals that share a net (net names do not matter), plus how many true
  nets are reproduced exactly
- behaviour: the simulator is built from the transcription and driven through the healthy
  sequence (power on, forward start, star to delta, stop, reverse, interlock check, stop). Lamps,
  motor state and the voltage to N at every true terminal are compared step by step with the true
  circuit. Timer delay and thermal trip time are not drawn in the image; when the transcription
  leaves them out they are copied from the true file, so this checks wiring, not invisible numbers.

Raw replies, parsed YAML and scores go to runs/<stamp>_transcribe/. Cost goes to the spend ledger.
"""

import argparse
import base64
import json
import re
import sys
import time
from datetime import datetime
from itertools import combinations
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from probeforge.agent.client import MUSE_SPARK, make_client  # noqa: E402
from probeforge.agent.loop import _cost  # noqa: E402
from probeforge.eval.spend import SpendLedger, SpendLimitError  # noqa: E402
from probeforge.sim import Circuit  # noqa: E402
from probeforge.sim.netlist import TYPE_PARTS, Netlist  # noqa: E402
from probeforge.sim.schematic import render_png  # noqa: E402

CIRCUIT = ROOT / "scenarios" / "circuits" / "star_delta_reversing.yaml"
EST_PER_CALL_USD = 0.08

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
  "3": [S2:4, K1:14, K1:A1, H1:X1]
```

Reply with the complete YAML for the circuit in the image inside one ```yaml block."""

# healthy sequence: (label, action)
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


def extract_yaml(text: str) -> str:
    m = re.search(r"```(?:yaml)?\s*\n(.*?)```", text or "", re.S)
    return m.group(1) if m else (text or "")


def pairs(nets: dict[str, list[str]]) -> set[frozenset]:
    return {frozenset(p) for ts in nets.values() for p in combinations(sorted(set(ts)), 2)}


def prf(found: set, true: set) -> dict:
    tp = len(found & true)
    return {"found": len(found), "true": len(true), "matched": tp,
            "precision": round(tp / len(found), 3) if found else 0.0, "recall": round(tp / len(true), 3) if true else 0.0}


def structure(data: dict, true_data: dict, true: Netlist) -> dict:
    comps = data.get("components") or {}
    true_comps = true_data["components"]

    def part_set(cs: dict) -> set[tuple]:
        out = set()
        for cid, spec in cs.items():
            if not isinstance(spec, dict):
                continue
            for key in TYPE_PARTS.get(spec.get("type"), {}):
                names = spec.get(key, [])
                for name in [names] if isinstance(names, str) else names or []:
                    out.add((str(cid), str(name), key))
        return out

    parts_found, parts_true = part_set(comps), part_set(true_comps)
    terms = lambda ps: {f"{c}:{t}" for c, n, _ in ps for t in n.split("-", 1)}  # noqa: E731
    nets = {str(k): [str(t) for t in v or []] for k, v in (data.get("nets") or {}).items()}
    found_sets = {frozenset(v) for v in nets.values()}
    exact = sum(frozenset(v) in found_sets for v in true.nets.values())
    return {
        "components": prf(set(map(str, comps)), set(true_comps)),
        "component_types_right": sum(isinstance(comps.get(c), dict) and comps[c].get("type") == s["type"]
                                     for c, s in true_comps.items()),
        "parts": prf(parts_found, parts_true),
        "parts_missing": sorted(f"{c}:{n} ({k})" for c, n, k in parts_true - parts_found),
        "parts_extra": sorted(f"{c}:{n} ({k})" for c, n, k in parts_found - parts_true),
        "terminals": prf(terms(parts_found), terms(parts_true)),
        "connections": prf(pairs(nets), pairs(true.nets)),
        "nets_exact": {"matched": exact, "true": len(true.nets)},
        "nets_wrong": [sorted(v) for v in true.nets.values() if frozenset(v) not in found_sets],
        "interlocks_right": sorted(map(sorted, data.get("interlocks") or [])) == sorted(map(sorted, true_data["interlocks"])),
    }


def fill_params(data: dict, true_data: dict) -> list[str]:
    filled = []
    for cid, spec in (data.get("components") or {}).items():
        t = true_data["components"].get(cid)
        if not (isinstance(spec, dict) and t):
            continue
        for k in ("delay", "trip_time", "rated_current"):
            if k in t and k not in spec:
                spec[k] = t[k]
                filled.append(f"{cid}.{k}")
    return filled


def trace(c: Circuit, terminals: list[str]) -> list[dict]:
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


def behaviour(data: dict, true: Netlist) -> dict:
    try:
        n = Netlist.from_dict({k: v for k, v in data.items() if k != "layout"})
    except Exception as e:  # noqa: BLE001 - any validation failure is the result
        return {"loads": False, "error": f"{type(e).__name__}: {e}"}
    terminals = sorted(true.terminal_net)
    try:
        got = trace(Circuit(n), terminals)
    except Exception as e:  # noqa: BLE001
        return {"loads": True, "runs": False, "error": f"{type(e).__name__}: {e}"}
    want = trace(Circuit(true), terminals)
    steps, v_ok, v_all = [], 0, 0
    for g, w in zip(got, want):
        same = g["lamps"] == w["lamps"] and g["motor"] == w["motor"]
        bad_v = [t for t in terminals if g["volts"][t] != w["volts"][t]]
        v_ok += len(terminals) - len(bad_v)
        v_all += len(terminals)
        steps.append({"step": w["step"], "panel_same": same, "motor": g["motor"], "true_motor": w["motor"],
                      "lamps": g["lamps"], "true_lamps": w["lamps"], "voltage_mismatches": bad_v})
    return {"loads": True, "runs": True, "panel_steps_same": sum(s["panel_same"] for s in steps), "steps": len(steps),
            "voltages_same": round(v_ok / v_all, 3), "sequence": steps}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    ledger = SpendLedger()
    try:
        ledger.check(args.runs * EST_PER_CALL_USD, force=args.force, what=f"{args.runs} transcription calls")
    except SpendLimitError as e:
        raise SystemExit(f"Refusing to start: {e}")
    true_data = yaml.safe_load(CIRCUIT.read_text(encoding="utf-8"))
    true = Netlist.load(CIRCUIT)
    png = base64.b64encode(render_png(true)).decode()
    out_dir = ROOT / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}_transcribe"
    out_dir.mkdir(parents=True)
    client = make_client()
    results = []
    for i in range(1, args.runs + 1):
        t0 = time.perf_counter()
        resp = client.chat.completions.create(
            model=MUSE_SPARK, reasoning_effort=args.effort,
            messages=[{"role": "user", "content": [{"type": "text", "text": SPEC},
                                                   {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png}"}}]}],
        )
        seconds = round(time.perf_counter() - t0, 1)
        u = resp.usage
        cached = (getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0)
        cost = _cost(MUSE_SPARK, u.prompt_tokens, cached, u.completion_tokens)
        ledger.record(cost, f"{out_dir.name}/run{i}")
        text = resp.choices[0].message.content or ""
        (out_dir / f"run{i}_reply.txt").write_text(text, encoding="utf-8")
        row = {"run": i, "seconds": seconds, "finish_reason": resp.choices[0].finish_reason,
               "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens, "cost_usd": round(cost, 4)}
        try:
            data = yaml.safe_load(extract_yaml(text))
            if not isinstance(data, dict):
                raise ValueError("reply is not a YAML mapping")
        except Exception as e:  # noqa: BLE001
            row["parse_error"] = f"{type(e).__name__}: {e}"
            results.append(row)
            print(json.dumps(row))
            continue
        row["structure"] = structure(data, true_data, true)
        row["params_filled_from_truth"] = fill_params(data, true_data)
        row["behaviour"] = behaviour(data, true)
        results.append(row)
        s, b = row["structure"], row["behaviour"]
        print(f"run {i}: components {s['components']['matched']}/{s['components']['true']} "
              f"parts P{s['parts']['precision']} R{s['parts']['recall']} "
              f"connections P{s['connections']['precision']} R{s['connections']['recall']} "
              f"nets exact {s['nets_exact']['matched']}/{s['nets_exact']['true']} "
              f"loads={b['loads']} panel {b.get('panel_steps_same', '-')}/{b.get('steps', '-')} "
              f"volts {b.get('voltages_same', '-')} ${cost:.3f} {seconds}s")
    (out_dir / "results.json").write_text(json.dumps({"args": vars(args), "model": MUSE_SPARK, "results": results},
                                                     indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved {out_dir}")


if __name__ == "__main__":
    main()
