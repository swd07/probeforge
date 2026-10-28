"""Compare a diagnosis with the injected fault. Only used after a run has finished.

"Correct" is pole level: component, failure mode and part (pole or contact) must all match. The
component-level number (component and failure mode, part ignored) is kept as a secondary score.
A diagnosis that names the right component and mode but leaves the part open ("pole ambiguous") is
not correct and not wrong; a diagnosis that asserts a wrong component, mode or part is.
"""

from probeforge.faults import Fault


def _norm(s) -> str:
    return str(s or "").strip().upper().replace(" ", "")


def _norm_part(part, component: str) -> str:
    p = _norm(part)
    prefix = _norm(component) + ":"
    if p.startswith(prefix):
        p = p[len(prefix):]
    return "-".join(sorted(p.split("-"))) if p else ""


def parse_fault(text: str) -> Fault:
    """'KM1:3-4 stuck_open' or 'FU1 blown' -> Fault."""
    target, mode = text.split()
    comp, _, part = target.partition(":")
    return Fault(comp, mode, part or None)


def score(diagnosis: dict | None, fault: Fault) -> dict:
    if not diagnosis or diagnosis.get("outcome") != "diagnosed":
        return {"component_ok": False, "mode_ok": False, "part_ok": False}
    component_ok = _norm(diagnosis.get("component")) == _norm(fault.component)
    mode_ok = component_ok and str(diagnosis.get("failure_mode", "")).strip() == fault.mode
    # whole-device faults have no part: accept an empty part or the part field left out
    part_ok = component_ok and _norm_part(diagnosis.get("part"), fault.component) == _norm_part(fault.part, fault.component)
    return {"component_ok": component_ok, "mode_ok": mode_ok, "part_ok": part_ok}


def grade(diagnosis: dict | None, fault: Fault, latent: bool, twins: list[Fault] | None = None) -> dict:
    """Every score the tables use, from one place."""
    from probeforge.eval.ambiguity import justified

    s = score(diagnosis, fault)
    s["part_given"] = bool(_norm_part((diagnosis or {}).get("part"), fault.component))
    outcome = (diagnosis or {}).get("outcome")
    honest_latent = latent and outcome == "insufficient_information"
    correct = (s["component_ok"] and s["mode_ok"] and s["part_ok"]) or honest_latent
    correct_component = (s["component_ok"] and s["mode_ok"]) or honest_latent
    diagnosed = outcome == "diagnosed"
    pole_open = diagnosed and not correct and s["component_ok"] and s["mode_ok"] and not s["part_given"]
    just = justified(diagnosis, fault, twins or [], correct)
    asserted_wrong = diagnosed and not correct and not pole_open
    return {**s, "correct": correct, "correct_component": correct_component, "pole_open": pole_open,
            "justified": just, "confident_wrong": asserted_wrong and not just}
