"""ATS agent profile: Muse Spark plans, the ATS toolbox measures, the four-tier policy guards.

A separate profile from the relay-panel agent (probeforge.agent, unchanged): its own prompt (probeforge.ats.prompts)
and tool specs (probeforge.ats.tools), the same loop protocol (native tool calls, text-markup recovery, nudges, at
most 3 meter readings per turn, turns-left warnings). Shared helpers (cost, run record, markup regexes) are imported,
not copied.
"""

import base64
import json
import time
from collections.abc import Callable

from probeforge.agent.client import MUSE_SPARK
from probeforge.agent.loop import (IMAGE_DROPPED_NOTE, INVOKE_RE, MAX_CONSECUTIVE_NUDGES, MAX_MEASUREMENTS_PER_TURN,
                                   PARAM_RE, WARN_AT_TURNS_LEFT, AgentRun, _cost)
from probeforge.ats.bench import AtsBench
from probeforge.ats.prompts import NUDGE, SYSTEM_PROMPT, TOO_MANY_MEASUREMENTS, initial_user_text, turns_left_warning
from probeforge.ats.tools import MEASUREMENT_TOOLS, TOOL_SPECS, Approver, AtsToolBox, approve_standard_only
from probeforge.sim.schematic import render_png

READING_LISTS = {"manual_operation_check": "readings", "repeat_transfer_attempt": "measure_during"}
STRING_PARAMS = {t["function"]["name"]: {k for k, v in t["function"]["parameters"]["properties"].items()
                                         if v.get("type") == "string"} for t in TOOL_SPECS}


def recover_text_tool_calls(text: str) -> list[dict]:
    """Tool calls the model wrote as text markup, as OpenAI-style tool_calls (ATS tool names)."""
    calls = []
    for i, m in enumerate(INVOKE_RE.finditer(text or "")):
        name = m.group(2)
        if name not in STRING_PARAMS:
            continue
        args = {}
        for key, raw in PARAM_RE.findall(m.group(3)):
            raw = raw.strip()
            if key in STRING_PARAMS[name]:
                args[key] = raw
                continue
            try:
                args[key] = json.loads(raw)
            except ValueError:
                args[key] = raw
        calls.append({"id": f"recovered_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}})
    return calls


def readings_in(name: str, args: dict) -> int:
    if name in MEASUREMENT_TOOLS:
        return 1
    items = args.get(READING_LISTS.get(name, ""))
    return len(items) if isinstance(items, list) else 0


def build_initial_messages(toolbox: AtsToolBox, max_turns: int = 30, include_image: bool = True) -> list[dict]:
    netlist = toolbox.bench.n
    observation = toolbox.initial_observation()
    system = {"role": "system", "content": SYSTEM_PROMPT.format(policy=toolbox.policy.summary(), max_turns=max_turns)}
    text = initial_user_text(observation, netlist.to_text())
    if not include_image:
        return [system, {"role": "user", "content": [{"type": "text", "text": text.replace(" (the image shows the same circuit)", "")}]}]
    png = base64.b64encode(render_png(netlist)).decode()
    return [system, {"role": "user", "content": [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png}"}}]}]


def run_ats_agent(bench: AtsBench, client, model: str = MUSE_SPARK, effort: str | None = "low", max_turns: int = 30,
                  approver: Approver = approve_standard_only, on_event: Callable[[dict], None] | None = None,
                  include_image: bool = True) -> tuple[AgentRun, AtsToolBox]:
    """Run one ATS diagnosis session on a bench already in its scenario state (fault applied, outage running).
    The schematic image goes with the first request only; later requests carry the text netlist alone."""
    toolbox = AtsToolBox(bench, approver=approver, on_event=on_event)
    run = AgentRun(model=model, effort=effort)
    messages = build_initial_messages(toolbox, max_turns, include_image)
    extra = {"reasoning_effort": effort} if effort else {}
    started = time.perf_counter()
    consecutive_nudges = 0
    pending_update = False  # meter readings since the last update_hypotheses

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

            if turn == 1 and include_image:
                messages[1] = {"role": "user", "content": messages[1]["content"][0]["text"] + "\n\n" + IMAGE_DROPPED_NOTE}

            msg = resp.choices[0].message
            assistant = msg.model_dump(exclude_none=True)
            calls = [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments} for c in msg.tool_calls or []]
            if not calls:
                recovered = recover_text_tool_calls(msg.content or "")
                if recovered:
                    run.recovered_text_calls += len(recovered)
                    assistant = {"role": "assistant", "content": "", "tool_calls": recovered}
                    calls = [{"id": c["id"], "name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                             for c in recovered]
            messages.append(assistant)
            turn_entry = {"turn": turn, "latency_s": round(latency, 2), "prompt_tokens": prompt, "cached_tokens": cached,
                          "completion_tokens": completion, "text": msg.content or "", "tool_calls": []}
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
            # parallel readings in one turn are fine; readings from earlier turns need an update first
            pending = pending_update
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
                    n_meas = readings_in(name, args)
                    if (n_meas or name == "submit_diagnosis") and pending and not turn_updates and not counted_missing:
                        run.missing_hypothesis_updates += 1  # counted, not blocked
                        counted_missing = True
                    if measured_this_turn + n_meas > MAX_MEASUREMENTS_PER_TURN:
                        result = {"error": TOO_MANY_MEASUREMENTS}
                        run.protocol_errors += 1
                    else:
                        measured_this_turn += n_meas
                        before = toolbox.measurements
                        result = toolbox.call(name, args)
                        if toolbox.measurements > before:
                            pending_update = True
                        if name == "update_hypotheses" and "error" not in result:
                            pending_update = False
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
