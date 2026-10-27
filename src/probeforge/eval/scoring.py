"""Compare a diagnosis with the injected fault. Only used after a run has finished."""

from probeforge.faults import Fault


def _norm(s) -> str:
    return str(s or "").strip().upper().replace(" ", "")


def score(diagnosis: dict | None, fault: Fault) -> dict:
    if not diagnosis or diagnosis.get("outcome") != "diagnosed":
        return {"component_ok": False, "mode_ok": False, "part_ok": False}
    component_ok = _norm(diagnosis.get("component")) == _norm(fault.component)
    mode_ok = component_ok and str(diagnosis.get("failure_mode", "")).strip() == fault.mode
    # whole-device faults have no part: accept an empty part or the part field left out
    part_ok = component_ok and _norm(diagnosis.get("part")) == _norm(fault.part)
    return {"component_ok": component_ok, "mode_ok": mode_ok, "part_ok": part_ok}
