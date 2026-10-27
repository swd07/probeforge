"""Spend guard: cumulative Meta Model API cost in runs/spend.json.

Batches and UI agent runs check the ledger before calling the API and record
what each run actually cost. The ledger starts with the $21 spent before it
existed (Oct 27, from the run logs).
"""

import json
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = ROOT / "runs" / "spend.json"
INITIAL_USD = 21.0
LIMIT_USD = 110.0
EST_PER_AGENT_RUN_USD = 0.10  # clean holdout average was $0.068; leave headroom for long runs


class SpendLimitError(RuntimeError):
    pass


class SpendLedger:
    _lock = threading.Lock()

    def __init__(self, path: Path = DEFAULT_PATH, limit_usd: float = LIMIT_USD, initial_usd: float = INITIAL_USD):
        self.path = Path(path)
        self.limit_usd = limit_usd
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._write({
                "total_usd": initial_usd,
                "limit_usd": limit_usd,
                "entries": [{"when": datetime.now().isoformat(timespec="seconds"), "usd": initial_usd,
                             "what": "spent before the ledger existed (Oct 27, from run logs)"}],
            })

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @property
    def total(self) -> float:
        return self._read()["total_usd"]

    def check(self, estimate_usd: float, force: bool = False, what: str = "batch") -> None:
        total = self.total
        if total + estimate_usd > self.limit_usd and not force:
            raise SpendLimitError(
                f"{what} would cost about ${estimate_usd:.2f}; spent so far ${total:.2f}, limit ${self.limit_usd:.2f}. "
                "Use --force to run anyway."
            )

    def record(self, usd: float, what: str) -> float:
        with self._lock:
            data = self._read()
            data["total_usd"] = round(data["total_usd"] + usd, 4)
            data["entries"].append({"when": datetime.now().isoformat(timespec="seconds"), "usd": round(usd, 4), "what": what})
            self._write(data)
            return data["total_usd"]
