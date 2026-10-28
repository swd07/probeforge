"""Self-consistency flags: several reads of the same schematic, every disagreement becomes an uncertain region.

Usage:
  uv run python scripts/consensus_read.py --replies runs/<dir>/run1_reply.txt runs/<dir>/run2_reply.txt ... --name NAME
  uv run python scripts/consensus_read.py --live 3 [--image photo.jpg] --name NAME      (calls the API, medium effort)

Writes scenarios/transcriptions/NAME_consensus.yaml (the read that agrees most with the others, with its own
flags plus the disagreement regions in `uncertain`) and NAME_disagreement_flags.yaml (only the disagreement
regions, to add to another read with run_scenarios.py --extra-flags). Prints how the flags cover the wrong nets
(scored against the true file after the fact, for the report only).
"""

import argparse
from pathlib import Path

import yaml

from probeforge.agent.client import make_client
from probeforge.eval.spend import SpendLedger, SpendLimitError
from probeforge.hybrid.consensus import agreement, consensus
from probeforge.hybrid.llm import Usage, chat
from probeforge.hybrid.netlist_io import dump, flags_of, parse_reply, spec, wrong_nets
from probeforge.sim import Netlist
from probeforge.sim.schematic import render_png

ROOT = Path(__file__).resolve().parents[1]
CIRCUIT = ROOT / "scenarios" / "circuits" / "star_delta_reversing.yaml"
OUT = ROOT / "scenarios" / "transcriptions"
EST_PER_CALL_USD = 0.08


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replies", nargs="*", default=[], help="saved transcription replies (no API calls)")
    ap.add_argument("--live", type=int, default=0, help="read the schematic this many times now")
    ap.add_argument("--image", default=None, help="with --live: this image instead of the rendered PNG")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--name", required=True)
    args = ap.parse_args()

    texts = [(ROOT / r).read_text(encoding="utf-8") for r in args.replies]
    if args.live:
        ledger = SpendLedger()
        try:
            ledger.check(args.live * EST_PER_CALL_USD, what=f"{args.live} schematic reads")
        except SpendLimitError as e:
            raise SystemExit(f"Refusing to start: {e}")
        png = (ROOT / args.image).read_bytes() if args.image else render_png(Netlist.load(CIRCUIT))
        client, usage = make_client(), Usage(effort=args.effort)
        for i in range(args.live):
            texts.append(chat(client, usage, f"consensus read {i + 1}", spec(flags=True), png, args.effort))
        ledger.record(usage.cost_usd, f"consensus reads {args.name}")
        print(f"{args.live} reads, ${usage.cost_usd:.3f}")
    reads = [parse_reply(t) for t in texts]
    if len(reads) < 2:
        raise SystemExit("need at least two reads")
    model, extra, i = consensus(reads)

    sources = args.replies + [f"live read {k + 1}" for k in range(args.live)]
    head = (f"# Consensus of {len(reads)} Muse Spark reads of the same schematic ({', '.join(sources)}).\n"
            f"# Model netlist: read {i + 1} (agrees most with the others), copied unedited.\n"
            f"# uncertain: that read's own flags plus {len(extra)} regions where the reads disagree.\n")
    (OUT / f"{args.name}_consensus.yaml").write_text(head + dump(model) + "uncertain:\n" + "".join(
        f"  - {{terminals: [{', '.join(f['terminals'])}], reason: {yaml.safe_dump(f['reason'], default_style=chr(34)).strip()}}}\n"
        for f in model["uncertain"]), encoding="utf-8", newline="\n")
    (OUT / f"{args.name}_disagreement_flags.yaml").write_text(
        f"# Regions where {len(reads)} reads of the same schematic disagree ({', '.join(sources)}).\n"
        + yaml.safe_dump({"uncertain": extra}, sort_keys=False, width=200), encoding="utf-8", newline="\n")

    true = Netlist.load(CIRCUIT)
    for k, r in enumerate(reads):
        wrong = {t for n in wrong_nets(r, true) for t in n}
        own = {t for f in flags_of(r) for t in f["terminals"]}
        both = own | {t for f in extra for t in f["terminals"]}
        print(f"read {k + 1}: agreement {[round(agreement(r, o), 3) for o in reads]}, wrong nets {len(wrong_nets(r, true))}, "
              f"terminals of wrong nets covered: own flags {len(wrong & own)}/{len(wrong)}, "
              f"own + disagreement {len(wrong & both)}/{len(wrong)}")
    print(f"model: read {i + 1}; {len(extra)} disagreement regions; wrote {args.name}_consensus.yaml")


if __name__ == "__main__":
    main()
