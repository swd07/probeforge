"""Read step test: can Muse Spark transcribe the schematic image into our YAML netlist format?

Usage:  uv run python scripts/transcribe_schematic.py [--runs 3] [--effort medium] [--no-flags] [--image photo.jpg]

The model gets the same PNG the agent sees and a format spec (keys, part kinds, an example of a
different, tiny circuit), never the true YAML. With flags (default) it also lists the regions it is
unsure about. Each transcription is scored against the true file (probeforge.hybrid.netlist_io):

- components, parts (with their kind), terminals
- connections: pairs of terminals that share a net (net names do not matter), and true nets
  reproduced exactly
- behaviour: the healthy operating sequence on a simulator built from the transcription, compared
  with the true circuit (unprinted values copied from the true file, so this checks wiring)
- flags: how many uncertain regions touch a wrong net, and how many wrong nets are flagged

Raw replies and scores go to runs/<stamp>_transcribe/. Cost goes to the spend ledger.
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import yaml

from probeforge.agent.client import make_client
from probeforge.eval.spend import SpendLedger, SpendLimitError
from probeforge.hybrid.llm import Usage, chat
from probeforge.hybrid.netlist_io import behaviour, flags_of, parse_reply, score_flags, spec, structure
from probeforge.sim import Netlist
from probeforge.sim.schematic import render_png

ROOT = Path(__file__).resolve().parents[1]
CIRCUIT = ROOT / "scenarios" / "circuits" / "star_delta_reversing.yaml"
EST_PER_CALL_USD = 0.08


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--no-flags", action="store_true", help="the original prompt, without uncertain regions")
    ap.add_argument("--image", default=None, help="transcribe this image (e.g. a phone photo) instead of the rendered PNG")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    ledger = SpendLedger()
    try:
        ledger.check(args.runs * EST_PER_CALL_USD, force=args.force, what=f"{args.runs} transcription calls")
    except SpendLimitError as e:
        raise SystemExit(f"Refusing to start: {e}")
    true_data = yaml.safe_load(CIRCUIT.read_text(encoding="utf-8"))
    true = Netlist.load(CIRCUIT)
    png = (ROOT / args.image).read_bytes() if args.image else render_png(true)
    tag = ("" if args.no_flags else "_flags") + (f"_{Path(args.image).stem}" if args.image else "")
    out_dir = ROOT / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}_transcribe{tag}"
    out_dir.mkdir(parents=True)
    client = make_client()
    results = []
    for i in range(1, args.runs + 1):
        usage = Usage(effort=args.effort)
        t0 = time.perf_counter()
        text = chat(client, usage, "transcription", spec(flags=not args.no_flags), png, args.effort)
        seconds = round(time.perf_counter() - t0, 1)
        ledger.record(usage.cost_usd, f"{out_dir.name}/run{i}")
        (out_dir / f"run{i}_reply.txt").write_text(text, encoding="utf-8")
        row = {"run": i, "seconds": seconds, "prompt_tokens": usage.prompt_tokens,
               "completion_tokens": usage.completion_tokens, "cost_usd": round(usage.cost_usd, 4)}
        try:
            data = parse_reply(text)
        except Exception as e:  # noqa: BLE001
            row["parse_error"] = f"{type(e).__name__}: {e}"
            results.append(row)
            print(json.dumps(row))
            continue
        flags = flags_of(data)
        row["structure"] = structure(data, true_data, true)
        row["behaviour"] = behaviour(data, true, true_data)
        row["flags"] = flags
        row["flag_score"] = score_flags(flags, data, true)
        results.append(row)
        s, b, f = row["structure"], row["behaviour"], row["flag_score"]
        print(f"run {i}: components {s['components']['matched']}/{s['components']['true']} "
              f"parts P{s['parts']['precision']} R{s['parts']['recall']} "
              f"connections P{s['connections']['precision']} R{s['connections']['recall']} "
              f"nets exact {s['nets_exact']['matched']}/{s['nets_exact']['true']} "
              f"loads={b['loads']} panel {b.get('panel_steps_same', '-')}/{b.get('steps', '-')} "
              f"volts {b.get('voltages_same', '-')} flags {f['flags']} (on wrong nets {f['flags_on_wrong_nets']}, "
              f"wrong nets flagged {f['wrong_nets_flagged']}/{f['wrong_nets']}) ${usage.cost_usd:.3f} {seconds}s")
    (out_dir / "results.json").write_text(json.dumps({"args": vars(args), "results": results},
                                                     indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved {out_dir}")


if __name__ == "__main__":
    main()
