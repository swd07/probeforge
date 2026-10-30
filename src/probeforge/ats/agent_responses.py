"""ATS agent profile over the Meta Responses API (/v1/responses): the same agent as probeforge.ats.agent, only the
transport differs, so the model's reasoning carries across turns.

Stateless replay (decision D37): every request has store=False, include=["reasoning.encrypted_content"] and no
previous_response_id; it sends the instructions (the same system prompt) and our own complete input list: the first user
message (the schematic image only in the first request, then the same text note as the Chat agent), every returned
reasoning item (id, summary, encrypted content), assistant message and function_call item, and our function_call_output
items in call order. The whole session state (readings, approvals) stays local. Same tools (flattened to the Responses
format, schemas unchanged), prompts, policy, effort, per-turn rules and scoring as the Chat agent. Reasoning summaries
are not used (empty for muse-spark-1.3). A stable prompt_cache_key and prompt_cache_retention "24h" are this transport's
cache settings; costs are reported with and without the cached-input discount.
"""

import json
import time
from collections.abc import Callable

from probeforge.agent.client import MUSE_SPARK
from probeforge.agent.loop import IMAGE_DROPPED_NOTE, MAX_CONSECUTIVE_NUDGES, MAX_MEASUREMENTS_PER_TURN, WARN_AT_TURNS_LEFT, AgentRun, _cost
from probeforge.ats.agent import build_initial_messages, readings_in, recover_text_tool_calls
from probeforge.ats.bench import AtsBench
from probeforge.ats.prompts import NUDGE, TOO_MANY_MEASUREMENTS, turns_left_warning
from probeforge.ats.tools import TOOL_SPECS, Approver, AtsToolBox, approve_standard_only

CACHE_KEY = "probeforge-ats-agent"
TOOLS = [{"type": "function", "name": t["function"]["name"], "description": t["function"]["description"],
          "parameters": t["function"]["parameters"]} for t in TOOL_SPECS]


def first_input(messages: list[dict]) -> tuple[str, dict, dict | None]:
    """From the Chat agent's initial messages: the instructions, the first user message with the image, and the same
    message without it (sent from the second request on, with the Chat agent's note)."""
    system, user = messages[0]["content"], messages[1]
    parts = user["content"] if isinstance(user["content"], list) else [{"type": "text", "text": user["content"]}]
    text = next(p["text"] for p in parts if p["type"] == "text")
    image = next((p["image_url"]["url"] for p in parts if p["type"] == "image_url"), None)
    content = [{"type": "input_text", "text": text}] + ([{"type": "input_image", "image_url": image}] if image else [])
    first = {"role": "user", "content": content}
    later = {"role": "user", "content": [{"type": "input_text", "text": text + "\n\n" + IMAGE_DROPPED_NOTE}]} if image else None
    return system, first, later


def replay_items(output: list[dict]) -> list[dict]:
    """Returned output items as input items for the next request (stateless replay, in order)."""
    items = []
    for o in output:
        if o["type"] == "reasoning":
            items.append({"type": "reasoning", "id": o.get("id"), "summary": o.get("summary") or [],
                          "encrypted_content": o.get("encrypted_content")})
        elif o["type"] == "function_call":
            items.append({"type": "function_call", "call_id": o["call_id"], "name": o["name"], "arguments": o.get("arguments") or "{}"})
        elif o["type"] == "message":
            text = "".join(c.get("text", "") for c in o.get("content") or [] if c.get("type") == "output_text")
            items.append({"role": "assistant", "content": [{"type": "output_text", "text": text}]})
    # a reasoning item must be followed by an assistant message or a function_call before any user message
    if items and items[-1]["type" if "type" in items[-1] else "role"] == "reasoning":
        items.append({"role": "assistant", "content": [{"type": "output_text", "text": "(continuing)"}]})
    return items


def run_ats_agent_responses(bench: AtsBench, client, model: str = MUSE_SPARK, effort: str | None = "low",
                            max_turns: int = 30, approver: Approver = approve_standard_only,
                            on_event: Callable[[dict], None] | None = None,
                            include_image: bool = True) -> tuple[AgentRun, AtsToolBox]:
    toolbox = AtsToolBox(bench, approver=approver, on_event=on_event)
    run = AgentRun(model=model, effort=effort)
    instructions, first, later = first_input(build_initial_messages(toolbox, max_turns, include_image))
    history: list[dict] = [first]
    extra = {"reasoning": {"effort": effort}} if effort else {}
    started = time.perf_counter()
    consecutive_nudges = 0
    pending_update = False

    try:
        for turn in range(1, max_turns + 1):
            t0 = time.perf_counter()
            resp = client.responses.create(model=model, instructions=instructions, input=history, tools=TOOLS,
                                           store=False, include=["reasoning.encrypted_content"],
                                           prompt_cache_key=CACHE_KEY, prompt_cache_retention="24h", **extra)
            latency = time.perf_counter() - t0
            u = resp.usage
            prompt = u.input_tokens if u else 0
            completion = u.output_tokens if u else 0
            cached = (getattr(u.input_tokens_details, "cached_tokens", 0) or 0) if u and u.input_tokens_details else 0
            reasoning = (getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0) if u and u.output_tokens_details else 0
            run.turns = turn
            run.prompt_tokens += prompt
            run.cached_tokens += cached
            run.completion_tokens += completion

            if turn == 1 and later is not None:
                history[0] = later  # the image goes with the first request only, as in the Chat agent

            output = [o.model_dump(exclude_none=True) for o in resp.output]
            text = "".join(c.get("text", "") for o in output if o["type"] == "message" for c in o.get("content") or []
                           if c.get("type") == "output_text")
            calls = [{"id": o["call_id"], "name": o["name"], "arguments": o.get("arguments") or "{}"}
                     for o in output if o["type"] == "function_call"]
            history += replay_items(output)
            if not calls:
                recovered = recover_text_tool_calls(text)
                if recovered:
                    run.recovered_text_calls += len(recovered)
                    for c in recovered:  # keep the history valid: a function_call item for every recovered call
                        history.append({"type": "function_call", "call_id": c["id"], "name": c["function"]["name"],
                                        "arguments": c["function"]["arguments"]})
                    calls = [{"id": c["id"], "name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                             for c in recovered]
            turn_entry = {"turn": turn, "latency_s": round(latency, 2), "prompt_tokens": prompt, "cached_tokens": cached,
                          "completion_tokens": completion, "reasoning_tokens": reasoning, "text": text, "tool_calls": []}
            run.turn_log.append(turn_entry)
            if on_event:
                on_event({"type": "turn", **{k: v for k, v in turn_entry.items() if k != "tool_calls"}})

            if not calls:
                run.nudges += 1
                consecutive_nudges += 1
                if consecutive_nudges > MAX_CONSECUTIVE_NUDGES:
                    break
                history.append({"role": "user", "content": [{"type": "input_text", "text": NUDGE}]})
                continue
            consecutive_nudges = 0

            turn_updates = any(c["name"] == "update_hypotheses" for c in calls)
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
                        run.missing_hypothesis_updates += 1
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
                history.append({"type": "function_call_output", "call_id": call["id"], "output": json.dumps(result)})

            if toolbox.diagnosis is not None:
                run.diagnosis = toolbox.diagnosis
                run.outcome = toolbox.diagnosis.get("outcome", "diagnosed")
                break
            left = max_turns - turn
            if left in WARN_AT_TURNS_LEFT:
                history.append({"role": "user", "content": [{"type": "input_text", "text": turns_left_warning(left)}]})
    except Exception as e:  # API or simulator failure: keep the partial trace (the session state is local)
        run.outcome = "error"
        run.error = f"{type(e).__name__}: {e}"

    run.seconds = round(time.perf_counter() - started, 2)
    run.cost_usd = round(_cost(model, run.prompt_tokens, run.cached_tokens, run.completion_tokens), 4)
    run.messages = history
    return run, toolbox
