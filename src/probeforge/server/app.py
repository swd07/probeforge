"""Web backend: live agent sessions and manual (human engineer) sessions over one WebSocket.

The browser never receives the injected fault while a session runs: tool events carry
what the actor saw (the same results the agent gets), panel snapshots carry what an
operator sees on the front panel. The fault, its observational twins and the true live
wiring are sent only in the final "done" event.

Protocol (JSON over /ws):
  client -> server  (every start may carry "bench": "ats" for the ASCO transfer switch bench, server/ats.py)
                    {"action": "start", "source": "scenario" | "random", "scenario": "s01",
                     "effort": "low", "include_latent": false, "fault": optional test hook}
                    {"action": "start_manual", ... same fault choice ..., "engineer": "name"}
                    {"action": "start_hybrid", ... same fault choice ..., "schematic": "saved" | "live"}
                    {"action": "flags", "id": 1, "approve": true}        (confirm flagged transcription regions)
                    {"action": "wiring", "id": 1, "choice": 0 | null}   (which wiring of a flagged region is real)
                    {"action": "tool", "name": "measure_voltage", "args": {...}}      (manual mode)
                    {"action": "approval", "id": 1, "approve": true}
                    {"action": "compare"}                                           (after a manual run)
                    {"action": "stop"}
  server -> client  session, turn, tool, hypotheses, approval_request, approval_answer, done,
                    stopped (the user ended the session), saved, compare_progress, compare, error;
                    hybrid also: stage, transcription, flags_request, flags_answer, conflict, correction,
                    correction_rejected, wiring_check, wiring_request, wiring_answer
"""

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from probeforge.server import access, ats, level1, settings, ui_runs
from probeforge.server.level1 import (  # noqa: F401 - re-exported (tests and scripts use app.<name>)
    ROOT, AgentSession, HybridSession, ManualSession, Session, pick_fault)

app = FastAPI(title="ProbeForge")

# Blocking work runs in two bounded pools (audit S1): tool calls, one in flight per connection, and runs (agent,
# hybrid, Compare), refused when all are busy. A connection holds two tool workers at most (a pending approval and one
# queued call), and
# connections are capped overall and per IP, so one visitor cannot starve the others.
TOOL_POOL = ThreadPoolExecutor(max_workers=settings.TOOL_WORKERS, thread_name_prefix="tool")
JOB_POOL = ThreadPoolExecutor(max_workers=settings.JOB_WORKERS, thread_name_prefix="job")
_jobs = {"running": 0}
_jobs_lock = threading.Lock()
_connections: dict[str, int] = {}


@app.get("/api/meta")
def meta() -> dict:
    return level1.meta()


ACTIONS = {"start", "start_manual", "start_hybrid", "tool", "compare", "suggest", "approval", "flags", "wiring", "stop"}


def message_problem(msg) -> str | None:
    """Why a client message cannot be handled, or None (audit S4: validated before dispatch)."""
    if not isinstance(msg, dict):
        return "not a JSON object"
    action = msg.get("action")
    if action not in ACTIONS:
        return "unknown action"
    if action in ("approval", "flags", "wiring") and (not isinstance(msg.get("id"), int) or isinstance(msg.get("id"), bool)):
        return "id must be an integer"
    if action in ("approval", "flags") and not isinstance(msg.get("approve", False), bool):
        return "approve must be true or false"
    if action == "tool" and (not isinstance(msg.get("name"), str) or not isinstance(msg.get("args", {}), dict)):
        return "a tool call needs a name and an args object"
    for key in ("token", "source", "scenario", "engineer", "schematic", "bench", "effort", "fault"):
        if key in msg and msg[key] is not None and not isinstance(msg[key], str):
            return f"{key} must be text"
    return None


@app.get("/api/session-token")
def session_token() -> dict:
    """A short-lived token the page sends with every start (server/access.py)."""
    return {"token": access.issue(), "ttl_s": access.TOKEN_TTL_S}


@app.get("/api/schematic")
def schematic() -> Response:
    return Response(level1.SVG, media_type="image/svg+xml")


@app.get("/api/ats/meta")
def ats_meta() -> dict:
    return ats.meta()


@app.get("/api/ats/troubleshooting")
def ats_troubleshooting() -> Response:
    """The troubleshooting sheet for families A and B (scripts/ats_troubleshooting.py), generated from the simulator."""
    path = ROOT / "docs" / "ATS_TROUBLESHOOTING.json"
    if not path.is_file():
        return Response("generate it first: scripts/ats_troubleshooting.py", status_code=404)
    return Response(path.read_text(encoding="utf-8"), media_type="application/json")


@app.get("/api/ats/schematic")
def ats_schematic() -> Response:
    return Response(ats.SVG, media_type="image/svg+xml")


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    ip = websocket.client.host if websocket.client else "?"
    if not access.origin_allowed(websocket.headers.get("origin"), websocket.headers.get("host")):
        await websocket.close(code=1008)  # policy violation: a page from another site
        return
    if sum(_connections.values()) >= settings.MAX_CONNECTIONS or _connections.get(ip, 0) >= settings.MAX_PER_IP:
        await websocket.close(code=1013)  # try again later
        return
    _connections[ip] = _connections.get(ip, 0) + 1
    await websocket.accept()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(ev: dict) -> None:
        if ev.get("type") == "done":
            ui_runs.record(session, "diagnosis")  # the local UI run list (D44), never sent to the agent
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    async def sender() -> None:
        while True:
            await websocket.send_json(await queue.get())

    pending = {"tool": 0}  # tool calls of this connection: one running plus one queued at most

    def background(fn, *args, run: bool = False) -> bool:
        """Run a blocking call in a worker thread; a crash reaches the browser as an error event. A tool call while
        two are pending (one waiting for an approval, say, and one queued) is refused; a run is refused when every
        run worker is busy. Returns whether it started."""
        if run:
            with _jobs_lock:
                if _jobs["running"] >= settings.JOB_WORKERS:
                    emit({"type": "error", "message": "The server is busy with other runs; try again in a minute."})
                    return False
                _jobs["running"] += 1
        elif pending["tool"] >= 2:
            emit({"type": "error", "message": "A step is still pending (an approval may be waiting): answer it or wait."})
            return False
        else:
            pending["tool"] += 1

        def job():
            try:
                fn(*args)
            except Exception as e:  # noqa: BLE001 - report anything, the session must not hang silently
                emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                if run:
                    with _jobs_lock:
                        _jobs["running"] -= 1
                else:
                    pending["tool"] -= 1
        loop.run_in_executor(JOB_POOL if run else TOOL_POOL, job)
        return True

    sender_task = asyncio.create_task(sender())
    session: Session | ats.AtsSession | None = None
    try:
        while True:
            try:
                text = await asyncio.wait_for(websocket.receive_text(), timeout=settings.IDLE_TIMEOUT_S)
            except asyncio.TimeoutError:
                emit({"type": "error", "message": f"Session closed after {settings.IDLE_TIMEOUT_S // 60} minutes without activity."})
                if session:
                    ui_runs.record(session, "idle timeout")
                    session.cancel(notify=False)
                await asyncio.sleep(0.2)  # let the message go out
                await websocket.close()
                break
            try:
                msg = json.loads(text)
            except ValueError:
                msg = None
            problem = message_problem(msg)
            if problem:  # audit S4: a bad message gets an error event; the socket and the session stay
                emit({"type": "error", "message": f"Ignored a malformed message ({problem})."})
                continue
            try:
                action = msg.get("action")
                if action in ("start", "start_manual", "start_hybrid"):
                    if not access.valid(msg.get("token")):
                        emit({"type": "error", "message": "The session token is missing or expired: reload the page."})
                        continue
                    ui_runs.record(session, "replaced by a new run")
                    if session and not session.done:
                        session.cancel(notify=False)
                    elif isinstance(session, ats.AtsSession):
                        session.cancel(notify=False)  # close a finished ATS session's intervention
                    if msg.get("bench") == "ats":
                        try:
                            session = ats.start_session(action, msg, emit, level1.client)
                        except (ValueError, KeyError) as e:
                            emit({"type": "error", "message": str(e)})
                            session = None
                            continue
                        if isinstance(session, (ats.AtsAgentSession, ats.AtsHybridSession)):
                            if not background(session.run, run=True):
                                session = None
                        else:
                            session.start()
                        continue
                    try:
                        fault, source = pick_fault(msg)
                    except (ValueError, KeyError) as e:
                        emit({"type": "error", "message": str(e)})
                        continue
                    if action == "start":
                        session = AgentSession(fault, source, settings.agent_effort(msg.get("effort")), emit)
                        if not background(session.run, run=True):
                            session = None
                    elif action == "start_hybrid":
                        session = HybridSession(fault, source, str(msg.get("schematic") or "saved"), emit)
                        if not background(session.run, run=True):
                            session = None
                    else:
                        session = ManualSession(fault, source, str(msg.get("engineer") or ""), emit)
                        session.start()
                elif action == "tool" and isinstance(session, (ManualSession, ats.AtsSession)):
                    args = msg.get("args") if isinstance(msg.get("args"), dict) else {}
                    background(session.call, str(msg.get("name")), args)
                elif action == "tool":
                    emit({"type": "error", "message": "No engineer session is running: choose Engineer, pick a fault and press Start."})
                elif action == "compare" and isinstance(session, ManualSession):
                    background(session.compare, run=True)
                elif action == "compare" and isinstance(session, ats.AtsSession):
                    background(session.compare, level1.client, run=True)
                elif action == "suggest" and isinstance(session, ats.AtsManualSession):
                    background(session.suggest)
                elif action in ("approval", "flags") and session:
                    session.answer(int(msg["id"]), bool(msg.get("approve")))
                elif action == "wiring" and isinstance(session, HybridSession):
                    session.choose(int(msg["id"]), msg.get("choice"))
                elif action == "stop" and session:
                    ui_runs.record(session, "stopped")
                    session.cancel()
                elif action == "stop":
                    emit({"type": "error", "message": "No session is running."})
            except Exception as e:  # noqa: BLE001 - one bad message must not end the connection
                emit({"type": "error", "message": f"Could not handle that message ({type(e).__name__})."})
    except WebSocketDisconnect:
        pass
    finally:
        # however the connection ends (closed tab, network loss, server error), the session ends with it: no
        # orphaned approval waits or paid runs, and the local UI run list gets its row (audit S4)
        if session:
            ui_runs.record(session, "connection closed")
            session.cancel(notify=False)
        sender_task.cancel()
        _connections[ip] -= 1
        if not _connections[ip]:
            del _connections[ip]


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
