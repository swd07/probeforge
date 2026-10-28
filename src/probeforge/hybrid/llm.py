"""Small helpers for the hybrid pipeline's model calls and for describing planner readings in text."""

import base64
import time
from dataclasses import dataclass, field

from probeforge.agent.client import MUSE_SPARK
from probeforge.agent.loop import _cost

EM_DASH = chr(0x2014)  # replaced in model text (project style rule)


@dataclass
class Usage:
    """Accumulated over every model call of one hybrid run (same fields make_trace reads from an AgentRun)."""

    model: str = MUSE_SPARK
    effort: str | None = None
    turns: int = 0  # model calls
    protocol_errors: int = 0
    recovered_text_calls: int = 0
    missing_hypothesis_updates: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    turn_log: list[dict] = field(default_factory=list)


def chat(client, usage: Usage, purpose: str, text: str, png: bytes | None = None, effort: str = "medium") -> str:
    """One model call with optional image; tokens and cost go into usage."""
    content = [{"type": "text", "text": text}]
    if png is not None:
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}})
    t0 = time.perf_counter()
    resp = client.chat.completions.create(model=usage.model, reasoning_effort=effort,
                                          messages=[{"role": "user", "content": content}])
    u = resp.usage
    prompt = u.prompt_tokens if u else 0
    completion = u.completion_tokens if u else 0
    details = getattr(u, "prompt_tokens_details", None) if u else None
    cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
    cost = _cost(usage.model, prompt, cached, completion)
    usage.turns += 1
    usage.prompt_tokens += prompt
    usage.cached_tokens += cached
    usage.completion_tokens += completion
    usage.cost_usd += cost
    reply = (resp.choices[0].message.content or "").replace(EM_DASH, ", ")
    usage.turn_log.append({"turn": usage.turns, "purpose": purpose, "effort": effort, "prompt_tokens": prompt,
                           "cached_tokens": cached, "completion_tokens": completion, "cost_usd": round(cost, 5),
                           "latency_s": round(time.perf_counter() - t0, 1), "text": reply})
    return reply


# ------------------------------------------------------------------ readings as text

def view_text(v: tuple) -> str:
    lamps, motor, currents, amps, power = v
    on = [k for k, lit in lamps if lit]
    current = ", ".join(f"{k} {a} A" for k, a in amps) if amps else ", ".join(f"{k} {c}" for k, c in currents)
    return f"lamps lit: {', '.join(on) or 'none'}; motor {motor}; line currents {current}; power {'on' if power else 'off'}"


def action_text(tool: str, args: dict) -> str:
    if tool == "read_indicators":
        return "look at the panel"
    if tool == "measure_voltage":
        return f"voltmeter {args['point_a']} to {args['point_b']}"
    if tool == "measure_resistance":
        return f"ohmmeter {args['point_a']} to {args['point_b']} (power off)"
    if tool == "press_button":
        held = "".join(f", voltmeter {m['point_a']} to {m['point_b']} while held" for m in args.get("measure_while_held", []))
        return f"press {args['button']} for {args.get('hold_seconds', 0.2)} s{held}"
    if tool == "wait":
        return f"wait {args['seconds']} s"
    if tool == "set_power":
        return f"switch power {'on' if args['on'] else 'off'}"
    return f"{tool} {args}"


def outcome_text(tool: str, outcome) -> str:
    if isinstance(outcome, str) and outcome.startswith("simulation"):
        return outcome
    if tool == "measure_voltage":
        return f"{outcome} V"
    if tool == "measure_resistance":
        return "open" if outcome == "open" else f"{outcome} ohm"
    if tool == "press_button":
        held, volts, after = outcome
        reading = f"; reading while held: {', '.join(f'{v} V' for v in volts)}" if volts else ""
        return f"while held: {view_text(held)}{reading}; after release: {view_text(after)}"
    return view_text(outcome)
