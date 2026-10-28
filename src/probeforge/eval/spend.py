"""Spend guard: cumulative Meta Model API cost in runs/spend.json.

Batches and UI agent runs check the ledger before calling the API and record
what each run actually cost. The ledger starts with the $21 spent before it
existed (Oct 27, from the run logs).

Total limit $130. The last $20 is reserved for the public demo: batches and
scripts may spend up to $110; live UI runs (demo=True) may also use the
reserve, but at most DEMO_DAILY_USD per calendar day (env PROBEFORGE_DEMO_DAILY_USD).
"""

import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = ROOT / "runs" / "spend.json"
INITIAL_USD = 21.0
LIMIT_USD = 130.0
DEMO_RESERVE_USD = 20.0
DEMO_DAILY_USD = float(os.environ.get("PROBEFORGE_DEMO_DAILY_USD", "5"))
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

    @contextmanager
    def _file_lock(self, timeout_s: float = 30.0):
        """Cross-process lock (several batch scripts may record at once): a lock file created exclusively."""
        lock = self.path.with_suffix(".lock")
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except (FileExistsError, PermissionError):  # Windows: PermissionError while the holder deletes it
                if time.monotonic() > deadline:  # a crashed writer left it behind
                    lock.unlink(missing_ok=True)
                    continue
                time.sleep(0.02)
        try:
            yield
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a reader never sees a half-written file

    @property
    def total(self) -> float:
        return self._read()["total_usd"]

    def demo_today(self) -> float:
        today = datetime.now().date().isoformat()
        return sum(e["usd"] for e in self._read()["entries"] if e.get("demo") and e["when"].startswith(today))

    def check(self, estimate_usd: float, force: bool = False, what: str = "batch", demo: bool = False) -> None:
        total = self.total
        if demo:
            today = self.demo_today()
            if total + estimate_usd > self.limit_usd:
                raise SpendLimitError(f"{what}: spent ${total:.2f} of the ${self.limit_usd:.2f} total, demo runs are stopped.")
            if today + estimate_usd > DEMO_DAILY_USD:
                raise SpendLimitError(f"{what}: live demo runs used ${today:.2f} of the ${DEMO_DAILY_USD:.2f} daily cap today.")
            return
        cap = self.limit_usd - DEMO_RESERVE_USD
        if total + estimate_usd > cap and not force:
            raise SpendLimitError(
                f"{what} would cost about ${estimate_usd:.2f}; spent so far ${total:.2f}, limit for batches ${cap:.2f} "
                f"(${DEMO_RESERVE_USD:.0f} of ${self.limit_usd:.0f} reserved for the public demo). Use --force to run anyway."
            )

    def record(self, usd: float, what: str, demo: bool = False) -> float:
        with self._lock, self._file_lock():
            data = self._read()
            data["total_usd"] = round(data["total_usd"] + usd, 4)
            data["limit_usd"] = self.limit_usd
            entry = {"when": datetime.now().isoformat(timespec="seconds"), "usd": round(usd, 4), "what": what}
            if demo:
                entry["demo"] = True
            data["entries"].append(entry)
            self._write(data)
            return data["total_usd"]
