"""Agent loop: Muse Spark plans, the toolbox measures, the policy guards."""

import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from probeforge.agent.client import MUSE_SPARK
from probeforge.agent.prompts import HYPOTHESES_FIRST, NUDGE, SYSTEM_PROMPT, initial_user_text
from probeforge.sim import Circuit
from probeforge.sim.schematic import render_png
from probeforge.tools.toolbox import MEASUREMENT_TOOLS, TOOL_SPECS, Approver, ToolBox, deny_all

# USD per 1M tokens, https://dev.meta.ai/docs/pricing-rate-limits (2026-10-27)
PRICES = {
    "muse-spark-1.3": {"input": 1.25, "cached": 0.15, "output": 4.25},
    "muse-wonder-1.0": {"input": 4.00, "cached": 0.20, "output": 20.00},
}
MAX_CONSECUTIVE_NUDGES = 3


@dataclass
class AgentRun:
    model: str
    effort: str | None
    outcome: str = "no_diagnosis"  # diagnosed, insufficient_information, no_diagnosis, error
    diagnosis: dict | None = None
    turns: int = 0
    nudges: int = 0
    protocol_errors: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str | None = None
    turn_log: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)


def _cost(model: str, prompt: int, cached: int, completion: int) -> float:
    p = PRICES.get(model)
    if not p:
        return 0.0
    return ((prompt - cached) * p["input"] + cached * p["cached"] + completion * p["output"]) / 1e6


def build_initial_messages(toolbox: ToolBox) -> list[dict]:
    """System and first user message: symptoms, schematic image, text netlist, policy summary."""
    netlist = toolbox.circuit.netlist
    indicators = toolbox.initial_observation()
    png = base64.b64encode(render_png(netlist)).decode()
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(policy=toolbox.policy.summary())},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": initial_user_text(indicators, netlist.to_text())},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png}"}},
            ],
        },
    ]


def run_agent(
    circuit: Circuit,
    client,
    model: str = MUSE_SPARK,
    effort: str | None = None,
    max_turns: int = 30,
    approver: Approver = deny_all,
    on_event: Callable[[dict], None] | None = None,
) -> tuple[AgentRun, ToolBox]:
    """Run one diagnosis session. The circuit should already be powered with its fault applied."""
    toolbox = ToolBox(circuit, approver=approver, on_event=on_event)
    run = AgentRun(model=model, effort=effort)
    messages = build_initial_messages(toolbox)
    extra = {"reasoning_effort": effort} if effort else {}
    started = time.perf_counter()
    consecutive_nudges = 0

    try:
        for turn in range(1, max_turns + 1):
            t0 = time.perf_counter()
            resp = client.chat.completions.create(model=model, messages=messages, tools=TOOL_SPECS, **extra)
            latency = time.perf_counter() - t0
            usage = resp.usage
            prompt = usage.prompt_tokens if usage else 0
            completion = usage.completion_tokens if usage else 0
            details = getattr(usage, "prompt_tokens_details", None) if usage else None
            cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
            run.turns = turn
            run.prompt_tokens += prompt
            run.cached_tokens += cached
            run.completion_tokens += completion

            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            messages.append(msg.model_dump(exclude_none=True))
            turn_entry = {
                "turn": turn,
                "latency_s": round(latency, 2),
                "prompt_tokens": prompt,
                "cached_tokens": cached,
                "completion_tokens": completion,
                "text": msg.content or "",
                "tool_calls": [],
            }
            run.turn_log.append(turn_entry)
            if on_event:
                on_event({"type": "turn", **{k: v for k, v in turn_entry.items() if k != "tool_calls"}})

            if not calls:
                run.nudges += 1
                consecutive_nudges += 1
                if consecutive_nudges > MAX_CONSECUTIVE_NUDGES:
                    break
                messages.append({"role": "user", "content": NUDGE})
                continue
            consecutive_nudges = 0

            turn_updates = any(c.function.name == "update_hypotheses" for c in calls)
            # parallel measurements in one turn are fine; results from earlier turns need an update first
            pending = toolbox.pending_hypotheses_update
            for call in calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                    if not isinstance(args, dict):
                        raise ValueError
                except ValueError:
                    result = {"error": "arguments are not a valid JSON object"}
                    run.protocol_errors += 1
                else:
                    needs_update = name in MEASUREMENT_TOOLS or name == "submit_diagnosis"
                    if needs_update and pending and not turn_updates:
                        result = {"error": HYPOTHESES_FIRST}
                        run.protocol_errors += 1
                    else:
                        result = toolbox.call(name, args)
                turn_entry["tool_calls"].append({"name": name, "arguments": call.function.arguments, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})

            if toolbox.diagnosis is not None:
                run.diagnosis = toolbox.diagnosis
                run.outcome = toolbox.diagnosis.get("outcome", "diagnosed")
                break
    except Exception as e:  # API or simulator failure: keep the partial trace
        run.outcome = "error"
        run.error = f"{type(e).__name__}: {e}"

    run.seconds = round(time.perf_counter() - started, 2)
    run.cost_usd = round(_cost(model, run.prompt_tokens, run.cached_tokens, run.completion_tokens), 4)
    run.messages = messages
    return run, toolbox
