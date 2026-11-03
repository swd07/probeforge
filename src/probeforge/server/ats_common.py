"""ATS web sessions, shared part: settings, the dev cases with their public ids, the fault pools and the background
warm-ups. Settings that tests replace (folders, the spend ledger, the warm-ups, the plan pause) are read by the other
modules as common.NAME at call time, so replacing them here takes effect everywhere."""

import json
import threading
import time
from pathlib import Path

import yaml

from probeforge.ats import transcriptions
from probeforge.ats.ambiguity import signature
from probeforge.ats.bench import AtsBench
from probeforge.ats.faults import all_faults
from probeforge.ats.hybrid.pipeline import healthy_sequence, warm
from probeforge.ats.hybrid.read import SHEET_DIR, SHEETS, to_netlist
from probeforge.ats.infogain import _scenario_benches
from probeforge.eval.metered import CALL_TIMEOUT_S, PUBLIC_MAX_COMPLETION_TOKENS, MeteredClient
from probeforge.eval.spend import server_ledger as ledger  # read as common.ledger() (tests replace it)
from probeforge.faults.model import Fault
from probeforge.server import settings
from probeforge.sim.schematic import render_svg

ROOT = Path(__file__).resolve().parents[3]
CASES_DIR = ROOT / "scenarios" / "ats"
ENGINEER_DIR = ROOT / "scenarios" / "engineer_traces" / "ats"
COMPARE_DIR = ROOT / "runs" / "compare"
# public mode: what visitors save in Engineer mode stays out of the recorded engineer traces (and out of Compare)
VISITOR_DIR = ROOT / "runs" / "visitor_traces" / "ats"
WARM_FILE = ROOT / "runs" / "warm.json"  # the last measured warm-up of the default saved read (the stage text's estimate)
BENCH = AtsBench()
NETLIST = BENCH.n
SVG = render_svg(NETLIST)
OUTAGE_S = 60.0  # every session starts 60 s after the Normal source failed (as the batch runs)
LIVE_V = 20.0
APPROVAL_TIMEOUT_S = settings.APPROVAL_TIMEOUT_S  # 120 s in public mode
FLOW = ["Fault detected", "Diagnosis in progress", "Root cause identified", "Awaiting authorized intervention",
        "Power restored", "Transfer verified"]
MANUAL_TOOLS = {"read_panel", "read_event_log", "read_metering", "read_position_indicator", "wait", "measure_voltage", "measure_resistance",
                "isolate_sources", "restore_sources", "manual_operation_check", "repeat_transfer_attempt",
                "perform_action", "submit_diagnosis"}
INTERVENTION_TOOLS = MANUAL_TOOLS - {"submit_diagnosis"}  # after the diagnosis, for the authorized person
EST_HYBRID_SAVED_USD = 0.02  # explanation only (recorded runs: about $0.006 per case)
EST_HYBRID_LIVE_USD = 1.00  # 3 reads plus up to 4 repairs (recorded model steps: $0.28 and $0.48)
PLAN_PAUSE_S = 1.0  # UI pace only: the plan stays on screen this long before the planner takes it (no effect on results)
LIVE_READ_TEXT = "about $0.30 to $1.00 and 4 to 7 minutes (3 Muse Spark reads of the drawing crops, then the model check)"


def _f(d: dict) -> Fault:
    return Fault(d["component"], d["mode"], d.get("part"))


def load_cases() -> dict[str, dict]:
    return {d["id"]: d for d in (yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(CASES_DIR.glob("*.yaml")))}


CASES = load_cases()
# the browser sees opaque ids until the result: the case file names describe the fault (a1_coil_open)
PUBLIC_IDS = {f"dev-{i:02d}": cid for i, cid in enumerate(CASES, 1)}
PUBLIC_OF = {cid: pub for pub, cid in PUBLIC_IDS.items()}


def _outage(faults: list[Fault]) -> AtsBench:
    b = AtsBench(faults=faults)
    b.lose_utility()
    b.step(OUTAGE_S)
    return b


def _face(b: AtsBench) -> tuple:
    i = b.indicators()
    return (tuple(sorted(i["lights"].items())), i["display"], tuple(i["alarms"]), i["generator"], i["load_powered"],
            tuple(i["metering"]["Emergency"]))


_visible: list[Fault] | None = None
_pool_lock = threading.Lock()


def visible_pool() -> list[Fault]:
    """Catalog faults that show on the controller panel during the outage (the random choice; faults that only
    matter on retransfer would look like a healthy switch)."""
    global _visible
    with _pool_lock:
        if _visible is None:
            healthy = _face(_outage([]))
            _visible = [f for f in all_faults(NETLIST) if _face(_outage([f])) != healthy]
    return _visible


_sigs: dict | None = None
_sig_lock = threading.Lock()


def catalog_signatures() -> dict:
    global _sigs
    visible_pool()  # the random choice needs it first
    with _sig_lock:
        if _sigs is None:
            _sigs = {f: signature([f]) for f in all_faults(NETLIST)}
    return _sigs


_sig_thread: threading.Thread | None = None


def warm_signatures() -> None:
    """Start the twin signatures in the background (about 15 s), needed only for the result card."""
    global _sig_thread
    if _sig_thread is None:
        _sig_thread = threading.Thread(target=catalog_signatures, daemon=True)
        _sig_thread.start()


_warm_lock = threading.Lock()
_warm_events: dict[str, threading.Event] = {}
_warm_started: dict[str, float] = {}


def warm_transcription(tid: str) -> threading.Event:
    """Simulate every candidate of a saved transcription in the background (once per transcription and server process;
    the frozen planner caches them by netlist content). The event is set when they are ready. The default read's
    duration is measured and kept (WARM_FILE) for the estimate in the stage text."""
    with _warm_lock:
        ev = _warm_events.get(tid)
        if ev is None:
            ev = _warm_events[tid] = threading.Event()
            _warm_started[tid] = time.monotonic()

            def job():
                try:
                    t = transcriptions.load(tid)
                    if healthy_sequence(to_netlist(t["data"]))[0]:
                        warm(t["data"], t["flags"])
                        if tid == transcriptions.DEFAULT:
                            save_warm_s(time.monotonic() - _warm_started[tid])
                finally:
                    ev.set()

            threading.Thread(target=job, daemon=True).start()
    return ev


def save_warm_s(seconds: float) -> None:
    try:
        WARM_FILE.parent.mkdir(parents=True, exist_ok=True)
        WARM_FILE.write_text(json.dumps({"transcription_s": round(seconds, 1)}), encoding="utf-8")
    except OSError:  # a read-only folder only loses the estimate
        pass


def measured_warm_s() -> float | None:
    try:
        return float(json.loads(WARM_FILE.read_text(encoding="utf-8"))["transcription_s"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def warm_stage_text(tid: str) -> str:
    """The stage shown while a Hybrid run waits for the simulation: the last measured duration on this server (or a
    range before the first measurement) and how long ago it started."""
    est = measured_warm_s()
    about = f"about {est:.0f} s" if est else "a few minutes"
    started = _warm_started.get(tid)
    ago = f"; started {time.monotonic() - started:.0f} s ago" if started is not None else ""
    return f"Simulating every candidate fault of the transcription (once per server start, {about}{ago})..."


def warm_suggestions() -> None:
    """The Engineer mode suggestion's candidates on our redrawing (the key suggest_next's planner uses)."""
    _scenario_benches(NETLIST, ("true", 0))


_start: dict = {"enabled": False, "t0": None, "done": threading.Event()}


def warm_at_start() -> None:
    """Public mode: simulate everything a first visitor would wait for (the default saved read, the Engineer
    suggestion, the twin signatures) before the proxy lets visitors in (/api/ready)."""
    _start["enabled"], _start["t0"] = True, time.monotonic()

    def job():
        try:
            warm_signatures()
            warm_transcription(transcriptions.DEFAULT).wait()
            warm_suggestions()
        finally:
            _start["done"].set()

    threading.Thread(target=job, daemon=True, name="warm-at-start").start()


def warm_status() -> dict:
    """Whether the start-up warm-up is done (always ready when it is off: local use warms on first use)."""
    if not _start["enabled"]:
        return {"ready": True, "warm_at_start": False}
    done = _start["done"].is_set()
    return {"ready": done, "warm_at_start": True, "elapsed_s": round(time.monotonic() - _start["t0"], 1),
            "estimate_s": measured_warm_s()}


def live_read_available() -> bool:
    return all((SHEET_DIR / s).exists() for s in SHEETS)


def metered(client, what: str, timeout_s: float = CALL_TIMEOUT_S) -> MeteredClient:
    """The model client of a live UI run: every call reserves and settles in the server ledger; in public mode with
    the per-call token cap (eval/metered.py has the values and their basis)."""
    return MeteredClient(client, ledger(), what, demo=True,
                         max_completion_tokens=PUBLIC_MAX_COMPLETION_TOKENS if settings.PUBLIC else None, timeout_s=timeout_s)
