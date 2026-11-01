"""ATS bench sessions for the web backend (agent and engineer), on the same WebSocket as the relay panel.

As for the relay panel, the browser never receives the injected fault while a session runs: tool events carry what
the actor saw, panel snapshots what a technician at the switch sees (the controller face, the sources, the load, the
UPS, the mechanism position flag). The fault, its observational twins and the true live nets are sent only in "done".

The hybrid session runs the frozen Hybrid v2 (probeforge.ats.hybrid) on a saved transcription (a recorded run's model
step, scenarios/transcriptions/ats/) or on a live re-read of the drawing crops (local only, cost shown first); the
planner's next step is sent before every reading (probeforge.ats.nextstep, read from the planner's update hook).

After the diagnosis the session stays open for the authorized intervention (isolate, repair, restore) through the
same toolbox and policy; the UPS status flow ends at "Transfer verified" only when the simulator confirms the load on
Emergency with the position confirmed by the controller.

The code is split by concern: ats_common (settings, cases, fault pools, warm-ups), ats_views (what the browser shows),
ats_session (the shared session), ats_modes (agent, Engineer, Hybrid v2). This module keeps meta() and pick() and
re-exports the rest, so `from probeforge.server import ats` keeps working.
"""

import random

from probeforge.agent.client import MUSE_SPARK
from probeforge.ats import transcriptions
from probeforge.ats.bench import REPAIR_KINDS
from probeforge.ats.faults import COMPONENT_MODES, PART_MODES, validate
from probeforge.ats.policy import RULES
from probeforge.faults.model import Fault
from probeforge.server import ats_common as common
from probeforge.server.ats_common import (  # noqa: F401 - re-exported
    BENCH, CASES, CASES_DIR, FLOW, INTERVENTION_TOOLS, LIVE_READ_TEXT, MANUAL_TOOLS, NETLIST, OUTAGE_S, PUBLIC_IDS,
    PUBLIC_OF, ROOT, SVG, _f, _outage, catalog_signatures, live_read_available, load_cases, visible_pool,
    warm_signatures, warm_transcription)
from probeforge.ats.tools import AtsToolBox  # noqa: F401 - re-exported
from probeforge.server.ats_modes import (  # noqa: F401 - re-exported
    SKIP_IN_REPLAY, AtsAgentSession, AtsHybridSession, AtsManualSession, start_session, suggest_next)
from probeforge.server.ats_session import AtsSession, Cancelled  # noqa: F401 - re-exported
from probeforge.server.ats_views import (  # noqa: F401 - re-exported
    TWIN_NOTE, column, describe, diagnosis_text, engineer_trace, sequence, snapshot, terminal_of)


def meta() -> dict:
    common.warm_signatures()  # the browser asks for meta when the ATS bench is chosen: precompute the pool and twins then
    common.warm_transcription(transcriptions.DEFAULT)
    comps = []
    for c in NETLIST.components.values():
        parts = [{"name": p.name, "kind": p.kind, "modes": list(PART_MODES.get(p.kind, ()))} for p in c.parts]
        modes = list(COMPONENT_MODES.get(c.type, ()))
        if modes or any(p["modes"] for p in parts):
            comps.append({"id": c.id, "type": c.type, "label": c.label, "modes": modes, "parts": parts})
    return {
        "model": MUSE_SPARK,
        "title": NETLIST.title,
        "neutral": "NN",
        # symptom only: the description would name the fault
        "scenarios": [{"id": PUBLIC_OF[cid], "symptom": c["symptom"]} for cid, c in CASES.items()],
        "components": comps,
        "repairs": {a: [p.id for p in NETLIST.parts.values() if p.kind in kinds] or ["CP"] for a, kinds in REPAIR_KINDS.items()},
        "limits": [{"action": a, "tier": t, "condition": c} for a, t, c in RULES],
        "ups_autonomy_s": BENCH.a["ups_autonomy_s"],
        "action_s": 30,
        "flow": FLOW,
        "transcriptions": transcriptions.available(),
        "default_transcription": transcriptions.DEFAULT,
        "live_read": {"available": live_read_available(), "estimate": LIVE_READ_TEXT},
    }


def pick(msg: dict) -> tuple[list[Fault], str, dict | None]:
    """Faults, where they came from, and the case (None for a random fault)."""
    if msg.get("fault"):  # test / demo hook (?fault= in the URL), never offered in the UI
        target, _, mode = str(msg["fault"]).strip().partition(" ")
        comp, _, part = target.partition(":")
        f = Fault(comp, mode.strip(), part or None)
        validate(NETLIST, f)
        return [f], "fault chosen by URL", None
    if msg.get("source") == "scenario":
        case = CASES[PUBLIC_IDS.get(msg["scenario"], msg["scenario"])]
        return [_f(x) for x in (case.get("faults") or [case["fault"]])], f"ATS dev scenario {PUBLIC_OF[case['id']]}", case
    pool = common.visible_pool()
    return [random.SystemRandom().choice(pool)], f"random ATS fault (any of the {len(pool)} visible on the panel)", None
