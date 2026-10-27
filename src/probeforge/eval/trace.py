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
