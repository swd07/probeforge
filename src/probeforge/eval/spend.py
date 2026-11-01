"""Spend guard: cumulative Meta Model API cost in runs/spend.json.

Batches and UI agent runs check the ledger before calling the API and record
what each run actually cost. The ledger starts with the $21 spent before it
existed (Oct 27, from the run logs).

Total limit $130. The last $20 is reserved for the public demo: batches and
scripts may spend up to $110; live UI runs (demo=True) may also use the
reserve, but at most DEMO_DAILY_USD per calendar day (env PROBEFORGE_DEMO_DAILY_USD).

Reserve, then settle (audit S6): `reserve()` checks the limits and writes a pending entry under a cross-process
lock, counting every open reservation; `settle()` replaces it with the actual cost. The metered client
(eval/metered.py) does this before every model call, so concurrent runs cannot pass on the same balance and a run
that fails midway still records what it spent. Reservations a crashed process left open expire after an hour.
It is a per-machine guard: the provider-side limit on the key is the real cap.

Public mode (PROBEFORGE_PUBLIC=1) uses a separate ledger, runs/public_spend.json, that starts at $0 on a fresh
server, with its own total (PROBEFORGE_PUBLIC_TOTAL_USD, default $30) and the same daily cap.
"""

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = ROOT / "runs" / "spend.json"
INITIAL_USD = 21.0
LIMIT_USD = 130.0
DEMO_RESERVE_USD = 20.0
DEMO_DAILY_USD = float(os.environ.get("PROBEFORGE_DEMO_DAILY_USD", "5"))
EST_PER_AGENT_RUN_USD = 0.12  # the S5 holdout agent mean ($0.12 per case; the most expensive run cost $0.30)
PUBLIC_PATH = ROOT / "runs" / "public_spend.json"
PUBLIC_TOTAL_USD = float(os.environ.get("PROBEFORGE_PUBLIC_TOTAL_USD", "30"))
RESERVATION_TTL_S = 3600


class SpendLimitError(RuntimeError):
    pass


class SpendLedger:
    _lock = threading.Lock()

    def __init__(self, path: Path = DEFAULT_PATH, limit_usd: float = LIMIT_USD, initial_usd: float = INITIAL_USD,
                 demo_reserve_usd: float = DEMO_RESERVE_USD):
        self.path = Path(path)
        self.limit_usd = limit_usd
        self.demo_reserve_usd = demo_reserve_usd
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._file_lock():
            if not self.path.exists():
                first = ([{"when": datetime.now().isoformat(timespec="seconds"), "usd": initial_usd,
                           "what": "spent before the ledger existed (Oct 27, from run logs)"}] if initial_usd else [])
                self._write({"total_usd": initial_usd, "limit_usd": limit_usd, "entries": first, "pending": {}})

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

    def demo_today(self, data: dict | None = None) -> float:
        today = datetime.now().date().isoformat()
        data = data or self._read()
        return sum(e["usd"] for e in data["entries"] if e.get("demo") and e["when"].startswith(today))

    @staticmethod
    def _open(data: dict, demo: bool | None = None) -> float:
        """Open reservations (all, or only demo ones), after dropping those a crashed process left behind."""
        pending = data.setdefault("pending", {})
        for rid in [r for r, p in pending.items() if time.time() - p["t"] > RESERVATION_TTL_S]:
            del pending[rid]
        return sum(p["usd"] for p in pending.values() if demo is None or p.get("demo") == demo)

    def check(self, estimate_usd: float, force: bool = False, what: str = "batch", demo: bool = False) -> None:
        with self._lock, self._file_lock():
            self._check(self._read(), estimate_usd, force, what, demo)

    def _check(self, data: dict, estimate_usd: float, force: bool, what: str, demo: bool) -> None:
        total = data["total_usd"] + self._open(data)
        if demo:
            today = self.demo_today(data) + self._open(data, demo=True)
            if total + estimate_usd > self.limit_usd:
                raise SpendLimitError(f"{what}: spent ${total:.2f} of the ${self.limit_usd:.2f} total, demo runs are stopped.")
            if today + estimate_usd > DEMO_DAILY_USD:
                raise SpendLimitError(f"{what}: live demo runs used ${today:.2f} of the ${DEMO_DAILY_USD:.2f} daily cap today.")
            return
        cap = self.limit_usd - self.demo_reserve_usd
        if total + estimate_usd > cap and not force:
            raise SpendLimitError(
                f"{what} would cost about ${estimate_usd:.2f}; spent so far ${total:.2f}, limit for batches ${cap:.2f} "
                f"(${self.demo_reserve_usd:.0f} of ${self.limit_usd:.0f} reserved for the public demo). Use --force to run anyway."
            )

    def reserve(self, estimate_usd: float, what: str, demo: bool = False, force: bool = False) -> str:
        """Check the limits against spent plus every open reservation, and hold estimate_usd until settle()."""
        with self._lock, self._file_lock():
            data = self._read()
            self._check(data, estimate_usd, force, what, demo)
            rid = uuid.uuid4().hex[:12]
            data["pending"][rid] = {"usd": round(estimate_usd, 4), "what": what, "demo": demo, "t": time.time()}
            self._write(data)
            return rid

    def settle(self, rid: str, usd: float, what: str | None = None) -> float:
        """Replace a reservation with the actual cost (0 for a call that failed before it was billed)."""
        with self._lock, self._file_lock():
            data = self._read()
            held = data.setdefault("pending", {}).pop(rid, {"what": what or "unreserved call", "demo": False})
            return self._append(data, usd, what or held["what"], held.get("demo", False))

    def record(self, usd: float, what: str, demo: bool = False) -> float:
        with self._lock, self._file_lock():
            return self._append(self._read(), usd, what, demo)

    def _append(self, data: dict, usd: float, what: str, demo: bool) -> float:
        data["total_usd"] = round(data["total_usd"] + usd, 4)
        data["limit_usd"] = self.limit_usd
        entry = {"when": datetime.now().isoformat(timespec="seconds"), "usd": round(usd, 4), "what": what}
        if demo:
            entry["demo"] = True
        data["entries"].append(entry)
        self._write(data)
        return data["total_usd"]


def server_ledger() -> SpendLedger:
    """The ledger live UI runs use: in public mode a separate one that starts at $0 on a fresh server."""
    if os.environ.get("PROBEFORGE_PUBLIC") == "1":
        return SpendLedger(PUBLIC_PATH, limit_usd=PUBLIC_TOTAL_USD, initial_usd=0.0, demo_reserve_usd=0.0)
    return SpendLedger()
