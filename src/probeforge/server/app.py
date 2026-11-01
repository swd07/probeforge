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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from probeforge.server import ats, level1, ui_runs
from probeforge.server.level1 import (  # noqa: F401 - re-exported (tests and scripts use app.<name>)
    ROOT, AgentSession, HybridSession, ManualSession, Session, pick_fault)

app = FastAPI(title="ProbeForge")


@app.get("/api/meta")
def meta() -> dict:
    return level1.meta()


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

    def background(fn, *args) -> None:
        """Run a blocking job in a worker thread; a crash reaches the browser as an error event."""
        def job():
            try:
                fn(*args)
            except Exception as e:  # noqa: BLE001 - report anything, the session must not hang silently
                emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
        loop.run_in_executor(None, job)

    sender_task = asyncio.create_task(sender())
    session: Session | ats.AtsSession | None = None
    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            if action in ("start", "start_manual", "start_hybrid"):
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
                        background(session.run)
                    else:
                        session.start()
                    continue
                try:
                    fault, source = pick_fault(msg)
                except (ValueError, KeyError) as e:
                    emit({"type": "error", "message": str(e)})
                    continue
                if action == "start":
                    session = AgentSession(fault, source, msg.get("effort") or "low", emit)
                    background(session.run)
                elif action == "start_hybrid":
                    session = HybridSession(fault, source, str(msg.get("schematic") or "saved"), emit)
                    background(session.run)
                else:
                    session = ManualSession(fault, source, str(msg.get("engineer") or ""), emit)
                    session.start()
            elif action == "tool" and isinstance(session, (ManualSession, ats.AtsSession)):
                args = msg.get("args") if isinstance(msg.get("args"), dict) else {}
                background(session.call, str(msg.get("name")), args)
            elif action == "tool":
                emit({"type": "error", "message": "No engineer session is running: choose Engineer, pick a fault and press Start."})
            elif action == "compare" and isinstance(session, ManualSession):
                background(session.compare)
            elif action == "compare" and isinstance(session, ats.AtsSession):
                background(session.compare, level1.client)
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
    except WebSocketDisconnect:
        if session:
            ui_runs.record(session, "browser left")
            session.cancel(notify=False)
    finally:
        sender_task.cancel()


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
