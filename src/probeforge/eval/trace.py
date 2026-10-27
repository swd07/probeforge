"""One trace format for agent, baseline and human runs, plus verdicts and side-by-side summaries."""

from probeforge.eval.ambiguity import justified, observational_twins
from probeforge.eval.scoring import score
from probeforge.faults import Fault
from probeforge.faults.catalog import has_visible_symptom
from probeforge.sim import Netlist
from probeforge.tools import ToolBox


def make_trace(*, case: str, runner: str, tb: ToolBox, diagnosis: dict | None, outcome: str, seconds: float,
               run=None, notes: list | None = None, extra: dict | None = None) -> dict:
    """The JSON written for every run. `run` is the AgentRun for agent runs, None otherwise.
    Never contains the injected fault: callers add it explicitly where a trace may hold it."""
    trace = {
        "case": case,
        "runner": runner,
        "model": run.model if run else None,
        "effort": run.effort if run else None,
        "outcome": outcome,
        "diagnosis": diagnosis,
        "turns": run.turns if run else 0,
        "protocol_errors": run.protocol_errors if run else 0,
        "recovered_text_calls": run.recovered_text_calls if run else 0,
        "missing_hypothesis_updates": run.missing_hypothesis_updates if run else 0,
        "measurements": tb.measurements,
        "redundant_measurements": tb.redundant_measurements,
        "tool_calls": tb.step,
        "policy": {
            "blocked": tb.policy.stats.blocked,
            "approval_requests": tb.policy.stats.approval_requests,
            "approvals_denied": tb.policy.stats.approvals_denied,
            "blocked_actions": tb.policy.stats.blocked_actions,
        },
        "tokens": {
            "prompt": run.prompt_tokens if run else 0,
            "cached": run.cached_tokens if run else 0,
            "completion": run.completion_tokens if run else 0,
        },
        "cost_usd": run.cost_usd if run else 0.0,
        "seconds": round(seconds, 1),
        "error": run.error if run else None,
        "notes": notes or [],
        "turn_log": run.turn_log if run else [],
        "tool_log": tb.log,
        "hypotheses_history": tb.hypotheses_history,
    }
    trace.update(extra or {})
    return trace


def verdict(netlist: Netlist, circuit_path: str, fault: Fault, diagnosis: dict | None, outcome: str) -> dict:
    s = score(diagnosis, fault)
    latent = not has_visible_symptom(netlist, fault)
    correct = (s["component_ok"] and s["mode_ok"]) or (latent and outcome == "insufficient_information")
    twins = observational_twins(str(circuit_path), fault)
    just = justified(diagnosis, fault, twins, correct)
    label = "correct" if correct else "justified" if just else ("no diagnosis" if outcome != "diagnosed" else "wrong")
    return {"verdict": label, "correct": correct, "latent": latent, "twins": [str(t) for t in twins], **s}


def describe_diagnosis(diagnosis: dict | None, outcome: str) -> str:
    if outcome != "diagnosed" or not diagnosis:
        return outcome.replace("_", " ")
    part = f" {diagnosis['part']}" if diagnosis.get("part") else ""
    return f"{diagnosis.get('component')}{part} {diagnosis.get('failure_mode')}"


def measurement_sequence(tool_log: list[dict]) -> list[str]:
    """Every meter reading in order, e.g. 'V 3 -> N: 230.0 V' or 'R KM1:A1 -> KM1:A2: open'."""
    seq = []
    for e in tool_log:
        r = e["result"]
        if not e["executed"]:
            if e["verdict"] == "block" and e["tool"].startswith("measure"):
                seq.append(f"blocked: {e['tool']} {e['args'].get('point_a')} -> {e['args'].get('point_b')}")
            continue
        if e["tool"] == "measure_voltage":
            seq.append(f"V {r['point_a']} -> {r['point_b']}: {r['volts']} V")
        elif e["tool"] == "measure_resistance":
            ohms = r["ohms"]
            seq.append(f"R {r['point_a']} -> {r['point_b']}: {ohms if ohms == 'open' else str(ohms) + ' ohm'}")
        elif e["tool"] == "press_button":
            for x in r.get("readings", []):
                seq.append(f"V {x['point_a']} -> {x['point_b']} (with {r['button']} held): {x['volts']} V")
    return seq


def summary(trace: dict, judged: dict) -> dict:
    """One column of the human / agent / baseline comparison."""
    return {
        "runner": trace["runner"],
        "diagnosis": describe_diagnosis(trace["diagnosis"], trace["outcome"]),
        "confidence": (trace["diagnosis"] or {}).get("confidence"),
        "verdict": judged["verdict"],
        "measurements": trace["measurements"],
        "redundant": trace["redundant_measurements"],
        "blocked": trace["policy"]["blocked"],
        "approvals": trace["policy"]["approval_requests"],
        "seconds": trace["seconds"],
        "cost_usd": trace["cost_usd"],
        "sequence": measurement_sequence(trace["tool_log"]),
    }


def _same_hypothesis(h: dict, diagnosis: dict) -> bool:
    if str(h.get("component", "")).upper() != str(diagnosis.get("component", "")).upper():
        return False
    if h.get("failure_mode") != diagnosis.get("failure_mode"):
        return False
    hp, dp = str(h.get("part") or ""), str(diagnosis.get("part") or "")
    return not hp or not dp or hp == dp


def _observation_text(e: dict) -> tuple[str, bool]:
    """Readable text for one logged step and whether it is a meter reading."""
    r = e["result"]
    if e["tool"] == "measure_voltage":
        return f"{r['point_a']} -> {r['point_b']}: {r['volts']} V", True
    if e["tool"] == "measure_resistance":
        ohms = r["ohms"]
        return f"{r['point_a']} -> {r['point_b']}: {ohms if ohms == 'open' else str(ohms) + ' ohm'}", True
    if e["tool"] == "press_button" and r.get("readings"):
        return "; ".join(f"{x['point_a']} -> {x['point_b']} with {r['button']} held: {x['volts']} V"
                         for x in r["readings"]), True
    if e["tool"] == "press_button":
        return f"press {r.get('button')}: motor {r['while_held']['motor']} while held, {r['after_release']['motor']} after", False
    if e["tool"] in ("wait", "read_indicators"):
        return f"{e['tool'].replace('_', ' ')}: motor {r.get('motor')}", False
    return e["tool"], False


def _readings(e: dict) -> list:
    r = e["result"]
    if e["tool"] == "measure_voltage":
        return [r["volts"]]
    if e["tool"] == "measure_resistance":
        return [r["ohms"]]
    if e["tool"] == "press_button":
        return [x["volts"] for x in r.get("readings", [])]
    return []


def healthy_readings(netlist: Netlist, tool_log: list[dict]) -> dict[int, list]:
    """Replay the logged actions on a fault-free circuit: what each reading would have been
    on a healthy panel. The electrician's expected value, computed from the schematic."""
    from probeforge.sim import Circuit

    c = Circuit(netlist)
    c.set_power(True)
    out: dict[int, list] = {}
    for e in tool_log:
        if not e["executed"] or e["step"] == 0:
            continue
        a, r, tool = e["args"], e["result"], e["tool"]
        try:
            if tool == "press_button":
                c.hold(r["button"])
                c.step(r["held_s"])
                out[e["step"]] = [c.voltage(x["point_a"], x["point_b"]) for x in r.get("readings", [])]
                c.release(r["button"])
            elif tool == "wait":
                c.step(min(max(float(a.get("seconds") or 0.1), 0.1), 30.0))
            elif tool == "set_power":
                c.set_power(bool(a.get("on")))
            elif tool == "perform_action" and a.get("action") == "reset_protection":
                c.reset(str(a.get("target")))
            elif tool == "measure_voltage":
                out[e["step"]] = [c.voltage(a["point_a"], a["point_b"])]
            elif tool == "measure_resistance":
                ohms = c.resistance(a["point_a"], a["point_b"])
                out[e["step"]] = ["open" if ohms == float("inf") else ohms]
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _differs(measured, healthy) -> bool:
    if isinstance(measured, str) or isinstance(healthy, str):
        return measured != healthy
    return abs(float(measured) - float(healthy)) > max(2.0, 0.05 * abs(float(healthy)))


def _most_cited(entries: list[dict], reason: str, healthy: dict[int, list]) -> dict:
    """Pick one observation: an abnormal reading (differs from a healthy panel) first, then the one
    the winning hypothesis' reason names most, then the one it mentions first, then the latest."""
    text = reason.upper()

    def score(item: tuple[int, dict]) -> tuple:
        index, e = item
        a, r = e["args"], e["result"]
        points = [a.get("point_a"), a.get("point_b")] + [x.get("point_a") for x in r.get("readings", [])]
        hits = [text.find(pt.upper()) for pt in points if pt and pt.upper() != "N" and pt.upper() in text]
        expected = healthy.get(e["step"], [])
        abnormal = any(_differs(m, h) for m, h in zip(_readings(e), expected))
        return (abnormal, len(hits), -min(hits, default=len(text)), index)

    return max(enumerate(entries), key=score)[1]


def decisive_measurement(tool_log: list[dict], hypotheses_history: list[dict], diagnosis: dict | None,
                         netlist: Netlist | None = None) -> dict | None:
    """The observation that raised the winning hypothesis the most.

    The winner is the submitted diagnosis. Each update_hypotheses call reflects every result
    the agent had seen before it, so the change in the winner's probability between two updates
    is credited to the observations made in between (meter readings preferred over panel checks).
    Returns None without a diagnosis or a hypothesis history (human runs keep no history).
    """
    if not diagnosis or diagnosis.get("outcome") != "diagnosed" or not hypotheses_history:
        return None
    healthy = healthy_readings(netlist, tool_log) if netlist else {}
    observed = [e for e in tool_log if e["executed"] and e["tool"] in
                ("measure_voltage", "measure_resistance", "press_button", "wait", "read_indicators")]
    best, prev_p, prev_step = None, 0.0, -1
    for update in hypotheses_history:
        p = max((h["probability"] for h in update["hypotheses"] if _same_hypothesis(h, diagnosis)), default=0.0)
        between = [e for e in observed if prev_step < e["step"] < update["step"]]
        meters = [e for e in between if _observation_text(e)[1]]
        cause = meters or between
        if cause and (best is None or p - prev_p > best["delta"]):
            reason = " ".join(h.get("reason", "") for h in update["hypotheses"] if _same_hypothesis(h, diagnosis))
            pick = _most_cited(cause, reason, healthy)
            expected = healthy.get(pick["step"])
            best = {
                "step": pick["step"],
                "reading": _observation_text(pick)[0],
                "healthy": ", ".join(f"{v} V" if pick["tool"] != "measure_resistance" else
                                     (v if v == "open" else f"{v} ohm") for v in expected) if expected else None,
                "meter": bool(meters),
                "shared_with": len(cause) - 1,  # other observations made since the previous update
                "reason": reason,
                "before": round(prev_p, 3),
                "after": round(p, 3),
                "delta": round(p - prev_p, 3),
            }
        prev_p, prev_step = p, update["step"]
    return best if best and best["delta"] > 0 else None
