"""Agent loop: Muse Spark plans, the toolbox measures, the policy guards."""

import base64
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from probeforge.agent.client import MUSE_SPARK
from probeforge.agent.prompts import (
    NUDGE,
    SYSTEM_PROMPT,
    TOO_MANY_MEASUREMENTS,
    initial_user_text,
    turns_left_warning,
)
from probeforge.sim import Circuit
from probeforge.sim.schematic import render_png
from probeforge.tools.toolbox import MEASUREMENT_TOOLS, TOOL_SPECS, Approver, ToolBox, deny_all

# USD per 1M tokens, https://dev.meta.ai/docs/pricing-rate-limits (2026-10-27)
PRICES = {
    "muse-spark-1.3": {"input": 1.25, "cached": 0.15, "output": 4.25},
    "muse-wonder-1.0": {"input": 4.00, "cached": 0.20, "output": 20.00},
}
MAX_CONSECUTIVE_NUDGES = 3
# Muse Spark sometimes writes a tool call as text markup instead of a native tool call:
#   <atem:function_calls><atem:invoke name="default.submit_diagnosis">
#   <atem:parameter name="confidence">0.9</atem:parameter> ... </atem:invoke></atem:function_calls>
INVOKE_RE = re.compile(r'<(\w+:)?invoke name="(?:\w+\.)?(\w+)">(.*?)</(?:\w+:)?invoke>', re.S)
PARAM_RE = re.compile(r'<(?:\w+:)?parameter name="(\w+)">(.*?)</(?:\w+:)?parameter>', re.S)
MAX_MEASUREMENTS_PER_TURN = 3
WARN_AT_TURNS_LEFT = (5, 2)
IMAGE_DROPPED_NOTE = "(The schematic image was attached to this message in your first turn; the text netlist above is the same circuit.)"


@dataclass
class AgentRun:
    model: str
    effort: str | None
    outcome: str = "no_diagnosis"  # diagnosed, insufficient_information, no_diagnosis, error
    diagnosis: dict | None = None
    turns: int = 0
    nudges: int = 0
    recovered_text_calls: int = 0  # tool calls the model wrote as text markup
    protocol_errors: int = 0
    missing_hypothesis_updates: int = 0  # turns that measured without updating hypotheses first
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


def recover_text_tool_calls(text: str) -> list[dict]:
    """Parse tool calls written as text markup into OpenAI-style tool_calls."""
    string_params = {
        t["function"]["name"]: {k for k, v in t["function"]["parameters"]["properties"].items() if v.get("type") == "string"}
        for t in TOOL_SPECS
    }
    calls = []
    for i, m in enumerate(INVOKE_RE.finditer(text or "")):
        name = m.group(2)
        if name not in string_params:
            continue
        args = {}
        for key, raw in PARAM_RE.findall(m.group(3)):
            raw = raw.strip()
            if key in string_params[name]:
                args[key] = raw
                continue
            try:
                args[key] = json.loads(raw)
            except ValueError:
                args[key] = raw
        calls.append({"id": f"recovered_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}})
    return calls


IMAGE_NOTE = " (the image shows the same circuit)"
NETLIST_HEADER = "Schematic text netlist (the image shows the same circuit):\n"
IMAGE_ONLY_HEADER = "Schematic: see the attached image.\n"
# image-only mode: the system prompt must not point to a netlist the agent does not have
IMAGE_ONLY_PROMPT_EDITS = [
    ("net names from the netlist (5, N, L1Q)", "wire numbers and net names printed in the schematic image (5, N, L1Q)"),
    ("(nominal resistances are in the netlist)",
     "(nominal resistances are not labeled in the schematic image: infer them from the component type or measure them)"),
    ("(timer delay and thermal trip time are in the netlist)",
     "(timer delay and thermal trip time are not labeled in the schematic image: infer them or find them by testing)"),
]


def system_prompt(policy: str, max_turns: int, include_netlist: bool = True) -> str:
    text = SYSTEM_PROMPT.format(policy=policy, max_turns=max_turns)
    if not include_netlist:
        for old, new in IMAGE_ONLY_PROMPT_EDITS:
            if old not in text:
                raise ValueError(f"image-only prompt edit no longer applies: {old!r}")
            text = text.replace(old, new)
    return text


def build_initial_messages(
    toolbox: ToolBox, max_turns: int = 30, include_image: bool = True, include_netlist: bool = True
) -> list[dict]:
    """System and first user message: symptoms, schematic image, text netlist, policy summary.

    include_image=False is the netlist-only ablation: no image part, and the note that an image
    shows the same circuit is dropped from the text. include_netlist=False is the image-only
    ablation: the netlist text is replaced by a pointer to the image. Everything else is identical."""
    if not (include_image or include_netlist):
        raise ValueError("the agent needs the image, the netlist or both")
    netlist = toolbox.circuit.netlist
    indicators = toolbox.initial_observation()
    system = {"role": "system", "content": system_prompt(toolbox.policy.summary(), max_turns, include_netlist)}
    if include_netlist:
        text = initial_user_text(indicators, netlist.to_text())
    else:
        text = initial_user_text(indicators, "").replace(NETLIST_HEADER, IMAGE_ONLY_HEADER).rstrip()
    if not include_image:
        return [system, {"role": "user", "content": [{"type": "text", "text": text.replace(IMAGE_NOTE, "")}]}]
    png = base64.b64encode(render_png(netlist)).decode()
    return [
        system,
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
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
    image_once: bool = True,
    include_image: bool = True,
    include_netlist: bool = True,
) -> tuple[AgentRun, ToolBox]:
    """Run one diagnosis session. The circuit should already be powered with its fault applied.

    image_once: send the schematic image only with the first request; later requests carry
    the text netlist alone (the API is stateless, so otherwise the image is re-sent every turn).
    Without the netlist the image is the only circuit description, so it is sent every turn and
    get_schematic (which returns the netlist text) answers with an error.
    """
    toolbox = ToolBox(circuit, approver=approver, on_event=on_event, text_netlist=include_netlist)
    run = AgentRun(model=model, effort=effort)
    messages = build_initial_messages(toolbox, max_turns, include_image, include_netlist)
    image_once = image_once and include_netlist
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

            if turn == 1 and image_once and include_image:
                text = messages[1]["content"][0]["text"]
                messages[1] = {"role": "user", "content": text + "\n\n" + IMAGE_DROPPED_NOTE}

            msg = resp.choices[0].message
            assistant = msg.model_dump(exclude_none=True)
            calls = [
                {"id": c.id, "name": c.function.name, "arguments": c.function.arguments} for c in msg.tool_calls or []
            ]
            if not calls:
                recovered = recover_text_tool_calls(msg.content or "")
                if recovered:
                    # keep the history valid: an assistant tool_calls message followed by tool results
                    run.recovered_text_calls += len(recovered)
                    assistant = {"role": "assistant", "content": "", "tool_calls": recovered}
                    calls = [{"id": c["id"], "name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                             for c in recovered]
            messages.append(assistant)
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

            turn_updates = any(c["name"] == "update_hypotheses" for c in calls)
            # parallel measurements in one turn are fine; results from earlier turns need an update first
            pending = toolbox.pending_hypotheses_update
            measured_this_turn = 0
            counted_missing = False
            for call in calls:
                name = call["name"]
                try:
                    args = json.loads(call["arguments"] or "{}")
                    if not isinstance(args, dict):
                        raise ValueError
                except ValueError:
                    result = {"error": "arguments are not a valid JSON object"}
                    run.protocol_errors += 1
                else:
                    readings = len(args.get("measure_while_held") or []) if name == "press_button" else 0
                    n_meas = 1 if name in MEASUREMENT_TOOLS else readings
                    needs_update = n_meas > 0 or name == "submit_diagnosis"
                    if needs_update and pending and not turn_updates and not counted_missing:
                        # not blocked: the call runs, the skipped update is only counted
                        run.missing_hypothesis_updates += 1
                        counted_missing = True
                    if measured_this_turn + n_meas > MAX_MEASUREMENTS_PER_TURN:
                        result = {"error": TOO_MANY_MEASUREMENTS}
                        run.protocol_errors += 1
                    else:
                        measured_this_turn += n_meas
                        result = toolbox.call(name, args)
                turn_entry["tool_calls"].append({"name": name, "arguments": call["arguments"], "result": result})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})

            if toolbox.diagnosis is not None:
                run.diagnosis = toolbox.diagnosis
                run.outcome = toolbox.diagnosis.get("outcome", "diagnosed")
                break
            left = max_turns - turn
            if left in WARN_AT_TURNS_LEFT:
                messages.append({"role": "user", "content": turns_left_warning(left)})
    except Exception as e:  # API or simulator failure: keep the partial trace
        run.outcome = "error"
        run.error = f"{type(e).__name__}: {e}"

    run.seconds = round(time.perf_counter() - started, 2)
    run.cost_usd = round(_cost(model, run.prompt_tokens, run.cached_tokens, run.completion_tokens), 4)
    run.messages = messages
    return run, toolbox
