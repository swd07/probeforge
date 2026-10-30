"""Re-score saved ATS drawing reads (no API calls): rebuild every reply in runs/<dir>/turns.json with the current
builder, rerun the consensus and score against the true netlist, also without the 52U region (not on the sheets).

  python -m uv run python scripts/ats_rescore_reads.py runs/<timestamp>_ats_reads
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ats_read_eval import score  # noqa: E402
from probeforge.ats import AtsBench  # noqa: E402
from probeforge.ats.hybrid.read import build, parse_reply  # noqa: E402
from probeforge.hybrid.consensus import consensus  # noqa: E402


def without_52u(s: dict, data: dict, true) -> dict:
    """Connections score with every true pair that involves a 52U terminal (not on the drawing sheets) and every
    pair with the builder's stand-in NSD left out."""
    from ats_read_eval import pairs, prf

    keep = lambda ps: {p for p in ps if not any(t.startswith(("52U:", "NSD:")) for t in p)}  # noqa: E731
    return prf(keep(pairs(data["nets"])), keep(pairs(true.nets)))


def main() -> None:
    d = Path(sys.argv[1])
    true = AtsBench().n
    turns = json.loads((d / "turns.json").read_text(encoding="utf-8"))
    reads = []
    for x in turns:
        if not x["purpose"].startswith("transcription"):
            continue
        try:
            reads.append(build(parse_reply(x["text"])))
        except Exception as e:  # noqa: BLE001
            print(f"{x['purpose']}: unusable ({type(e).__name__}: {e})")
    model, extra, i = consensus(reads) if len(reads) > 1 else (reads[0], [], 0)
    for k, data in enumerate(reads + [model]):
        s = score(data, true)
        c, p, w = s["connections"], s["parts"], without_52u(s, data, true)
        name = f"read {k + 1}" if k < len(reads) else f"consensus (read {i + 1})"
        print(f"{name}: parts P {p['precision']} R {p['recall']}, connections P {c['precision']} R {c['recall']} "
              f"(without 52U: P {w['precision']} R {w['recall']}), nets exact {s['nets_exact']['matched']}/{s['nets_exact']['true']}, "
              f"flags {s['flags']}")
        if k == len(reads):
            print("  consensus wrong nets:", s["nets_wrong"])
            print("  flags:", [f["terminals"] for f in data.get("uncertain") or []])


if __name__ == "__main__":
    main()
