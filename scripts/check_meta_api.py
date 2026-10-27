"""Day 1 checks for the Meta Model API.

Runs four checks against Muse Spark and prints a pass/fail summary plus
token usage per call:

1. tools:      one fake tool, expect parallel tool calls, then a full round trip
2. stream:     same tool with stream=True, rebuild arguments from deltas
3. structured: JSON schema output (hypothesis list) with strict=true
4. image:      a generated relay schematic PNG, ask for components and terminals

Usage:  uv run python scripts/check_meta_api.py [--model muse-spark-1.3] [--effort low]
A JSON report is written to runs/day1_api_check.json.
"""

import argparse
import base64
import io
import json
import time
import traceback
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from probeforge.agent.client import MUSE_SPARK, make_client

ROOT = Path(__file__).resolve().parents[1]

MEASURE_VOLTAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "measure_voltage",
        "description": "Measure AC voltage in volts between two terminals of the control circuit.",
        "parameters": {
            "type": "object",
            "properties": {
                "point_a": {"type": "string", "description": "Terminal id, e.g. 'FU1:2'"},
                "point_b": {"type": "string", "description": "Terminal id, e.g. 'N'"},
            },
            "required": ["point_a", "point_b"],
            "additionalProperties": False,
        },
    },
}

TOOL_PROMPT = (
    "You are testing a 230 V control circuit. Measure the voltage from FU1:1 to N "
    "and from FU1:2 to N. Make both measurements at once using parallel tool calls, "
    "then tell me whether the fuse FU1 is blown."
)

# Fake meter: supply present before the fuse, nothing after it (blown fuse).
FAKE_READINGS = {("FU1:1", "N"): 230.0, ("FU1:2", "N"): 0.0}

usage_log: list[dict] = []


def record_usage(check: str, usage) -> None:
    if usage is None:
        usage_log.append({"check": check, "prompt": None, "completion": None, "total": None})
        return
    usage_log.append(
        {
            "check": check,
            "prompt": usage.prompt_tokens,
            "completion": usage.completion_tokens,
            "total": usage.total_tokens,
        }
    )


def fake_measure(args: dict) -> float:
    key = (args.get("point_a", "").upper(), args.get("point_b", "").upper())
    return FAKE_READINGS.get(key, FAKE_READINGS.get((key[1], key[0]), 0.0))


def check_tools(client, model: str, extra: dict) -> dict:
    messages = [{"role": "user", "content": TOOL_PROMPT}]
    r1 = client.chat.completions.create(
        model=model, messages=messages, tools=[MEASURE_VOLTAGE_TOOL], **extra
    )
    record_usage("tools/call", r1.usage)
    msg = r1.choices[0].message
    calls = msg.tool_calls or []
    parsed = [json.loads(c.function.arguments) for c in calls]

    messages.append(msg.model_dump(exclude_none=True))
    for call, args in zip(calls, parsed):
        messages.append(
            {"role": "tool", "tool_call_id": call.id, "content": json.dumps({"volts": fake_measure(args)})}
        )
    r2 = client.chat.completions.create(
        model=model, messages=messages, tools=[MEASURE_VOLTAGE_TOOL], **extra
    )
    record_usage("tools/followup", r2.usage)
    answer = r2.choices[0].message.content or ""

    return {
        "ok": len(calls) >= 1 and "blown" in answer.lower(),
        "parallel": len(calls) >= 2,
        "finish_reason": r1.choices[0].finish_reason,
        "tool_calls": parsed,
        "final_answer": answer,
    }


def check_stream(client, model: str, extra: dict) -> dict:
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": TOOL_PROMPT}],
        tools=[MEASURE_VOLTAGE_TOOL],
        stream=True,
        stream_options={"include_usage": True},
        **extra,
    )
    stream = client.chat.completions.create(**kwargs)

    calls: dict[int, dict] = {}
    arg_deltas = 0
    usage = None
    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        for d in chunk.choices[0].delta.tool_calls or []:
            slot = calls.setdefault(d.index, {"name": "", "arguments": ""})
            if d.function and d.function.name:
                slot["name"] += d.function.name
            if d.function and d.function.arguments:
                slot["arguments"] += d.function.arguments
                arg_deltas += 1
    record_usage("stream", usage)

    parsed = [json.loads(c["arguments"]) for _, c in sorted(calls.items())]
    return {
        "ok": len(parsed) >= 1,
        "parallel": len(parsed) >= 2,
        "argument_deltas": arg_deltas,
        "tool_calls": parsed,
    }


HYPOTHESES_SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "component": {"type": "string"},
                    "failure_mode": {
                        "type": "string",
                        "enum": ["open", "short", "stuck_open", "stuck_closed", "welded", "tripped"],
                    },
                    "probability": {"type": "number"},
                },
                "required": ["component", "failure_mode", "probability"],
                "additionalProperties": False,
            },
        },
        "next_measurement": {"type": "string"},
    },
    "required": ["hypotheses", "next_measurement"],
    "additionalProperties": False,
}


def check_structured(client, model: str, extra: dict) -> dict:
    prompt = (
        "A motor starter control circuit: L1 -> fuse FU1 -> Stop button SB1 (NC) -> "
        "Start button SB2 (NO, with KM1 13-14 self-hold in parallel) -> thermal relay "
        "contact KK1 95-96 -> KM1 coil -> N. Symptom: pressing Start does nothing, the "
        "Power lamp (connected right after FU1) is ON. List the 3 most likely causes "
        "with probabilities summing to 1, and the single best next measurement."
    )
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "hypotheses", "schema": HYPOTHESES_SCHEMA, "strict": True},
        },
        **extra,
    )
    record_usage("structured", r.usage)
    data = json.loads(r.choices[0].message.content)
    hyps = data["hypotheses"]
    total_p = sum(h["probability"] for h in hyps)
    return {
        "ok": len(hyps) >= 1 and all(set(h) == {"component", "failure_mode", "probability"} for h in hyps),
        "probability_sum": round(total_p, 3),
        "top_is_not_fuse": bool(hyps) and "FU1" not in hyps[0]["component"].upper(),
        "output": data,
    }


# Ground truth for the generated schematic: label -> terminals drawn on it.
SCHEMATIC_TRUTH = {
    "FU1": {"1", "2"},
    "SB1": {"21", "22"},
    "SB2": {"13", "14"},
    "KM1": {"13", "14", "A1", "A2"},
    "KK1": {"95", "96"},
    "HL1": {"X1", "X2"},
}


def draw_schematic() -> bytes:
    """Draw a small ladder diagram of a start/stop circuit with self-hold."""
    W, H = 1100, 460
    img = Image.new("RGB", (W, H), "white")
    g = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=14)
    black = "black"
    lw = 3

    def text(x, y, s, f=font):
        g.text((x, y), s, fill=black, font=f, anchor="mm")

    def wire(x1, y1, x2, y2):
        g.line([(x1, y1), (x2, y2)], fill=black, width=lw)

    def dot(x, y):
        g.ellipse([x - 5, y - 5, x + 5, y + 5], fill=black)

    def contact(x, y, label, t1, t2, nc=False):
        # Ladder style: -| |- for NO, -|/|- for NC. Occupies x..x+60.
        wire(x, y, x + 20, y)
        wire(x + 20, y - 18, x + 20, y + 18)
        wire(x + 40, y - 18, x + 40, y + 18)
        wire(x + 40, y, x + 60, y)
        if nc:
            wire(x + 12, y + 22, x + 48, y - 22)
        text(x + 30, y - 34, label)
        text(x + 8, y + 26, t1, small)
        text(x + 52, y + 26, t2, small)

    def fuse(x, y, label):
        g.rectangle([x + 10, y - 10, x + 60, y + 10], outline=black, width=lw)
        wire(x, y, x + 70, y)
        text(x + 35, y - 30, label)
        text(x + 4, y + 22, "1", small)
        text(x + 66, y + 22, "2", small)

    def coil(x, y, label):
        wire(x, y, x + 15, y)
        g.rectangle([x + 15, y - 20, x + 65, y + 20], outline=black, width=lw)
        wire(x + 65, y, x + 80, y)
        text(x + 40, y - 38, label)
        text(x + 6, y + 30, "A1", small)
        text(x + 74, y + 30, "A2", small)

    def lamp(x, y, label):
        wire(x, y, x + 20, y)
        g.ellipse([x + 20, y - 20, x + 60, y + 20], outline=black, width=lw)
        wire(x + 26, y - 14, x + 54, y + 14)
        wire(x + 26, y + 14, x + 54, y - 14)
        wire(x + 60, y, x + 80, y)
        text(x + 40, y - 38, label + " (Power)")
        text(x + 6, y + 30, "X1", small)
        text(x + 74, y + 30, "X2", small)

    left, right = 60, 1040
    y1, y2, y3 = 130, 230, 360
    wire(left, 60, left, 420)
    wire(right, 60, right, 420)
    text(left, 40, "L1")
    text(right, 40, "N")

    # Rung 1: L1 - FU1 - SB1 - SB2 (|| KM1 13-14) - KK1 - KM1 coil - N
    wire(left, y1, 120, y1)
    fuse(120, y1, "FU1")
    wire(190, y1, 290, y1)
    dot(240, y1)
    text(256, y1 + 22, "1", small)
    contact(290, y1, "SB1 Stop", "21", "22", nc=True)
    wire(350, y1, 440, y1)
    dot(410, y1)
    text(395, y1 + 22, "2", small)
    contact(440, y1, "SB2 Start", "13", "14")
    wire(500, y1, 640, y1)
    dot(590, y1)
    text(605, y1 + 22, "3", small)
    # Self-hold branch in parallel with SB2
    wire(410, y1, 410, y2)
    wire(410, y2, 440, y2)
    contact(440, y2, "KM1", "13", "14")
    wire(500, y2, 590, y2)
    wire(590, y2, 590, y1)
    contact(640, y1, "KK1", "95", "96", nc=True)
    wire(700, y1, 800, y1)
    text(750, y1 + 22, "4", small)
    coil(800, y1, "KM1")
    wire(880, y1, right, y1)

    # Rung 2: Power lamp after the fuse
    wire(240, y1, 240, y3)
    wire(240, y3, 600, y3)
    lamp(600, y3, "HL1")
    wire(680, y3, right, y3)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


SCHEMATIC_SCHEMA = {
    "type": "object",
    "properties": {
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "kind": {"type": "string"},
                    "terminals": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["label", "kind", "terminals"],
                "additionalProperties": False,
            },
        },
        "wire_numbers": {"type": "array", "items": {"type": "string"}},
        "self_hold_contact_parallel_to": {"type": "string"},
    },
    "required": ["components", "wire_numbers", "self_hold_contact_parallel_to"],
    "additionalProperties": False,
}


def check_image(client, model: str, extra: dict) -> dict:
    png = draw_schematic()
    out = ROOT / "runs" / "day1_schematic.png"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(png)
    b64 = base64.b64encode(png).decode()

    prompt = (
        "This is a relay control circuit ladder diagram between L1 and N. List every "
        "component with its label (e.g. 'FU1'), its kind (fuse, NC contact, NO contact, "
        "coil, lamp) and the terminal numbers printed next to it. If one label appears "
        "several times (coil and auxiliary contact), merge its terminals into one entry. "
        "Also list the wire numbers and say which component the self-hold contact is "
        "wired in parallel with."
    )
    r = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "schematic", "schema": SCHEMATIC_SCHEMA, "strict": True},
        },
        **extra,
    )
    record_usage("image", r.usage)
    data = json.loads(r.choices[0].message.content)

    seen: dict[str, set[str]] = {}
    for c in data["components"]:
        label = c["label"].upper().split()[0] if c["label"].strip() else ""
        seen.setdefault(label, set()).update(t.upper() for t in c["terminals"])
    labels_found = sorted(set(SCHEMATIC_TRUTH) & set(seen))
    term_total = sum(len(t) for t in SCHEMATIC_TRUTH.values())
    term_hit = sum(len(SCHEMATIC_TRUTH[k] & seen.get(k, set())) for k in SCHEMATIC_TRUTH)
    parallel_ok = "SB2" in data["self_hold_contact_parallel_to"].upper()

    return {
        "ok": len(labels_found) == len(SCHEMATIC_TRUTH) and term_hit == term_total and parallel_ok,
        "labels_found": f"{len(labels_found)}/{len(SCHEMATIC_TRUTH)}",
        "terminals_found": f"{term_hit}/{term_total}",
        "self_hold_parallel_ok": parallel_ok,
        "output": data,
    }


CHECKS = {
    "tools": check_tools,
    "stream": check_stream,
    "structured": check_structured,
    "image": check_image,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MUSE_SPARK)
    ap.add_argument("--effort", default=None, help="reasoning_effort: minimal, low, medium, high, xhigh")
    ap.add_argument("--only", nargs="*", choices=list(CHECKS), default=list(CHECKS))
    args = ap.parse_args()

    client = make_client()
    extra = {"reasoning_effort": args.effort} if args.effort else {}
    report = {"model": args.model, "effort": args.effort, "checks": {}}

    for name in args.only:
        t0 = time.perf_counter()
        try:
            result = CHECKS[name](client, args.model, extra)
        except Exception as e:  # report and keep going so one failure does not hide the rest
            result = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}
        result["seconds"] = round(time.perf_counter() - t0, 2)
        report["checks"][name] = result
        status = "PASS" if result["ok"] else "FAIL"
        brief = {k: v for k, v in result.items() if k not in ("output", "trace", "final_answer")}
        print(f"[{status}] {name}: {json.dumps(brief, ensure_ascii=False)}")

    report["usage"] = usage_log
    report["total_tokens"] = sum(u["total"] or 0 for u in usage_log)
    print("\nToken usage:")
    for u in usage_log:
        print(f"  {u['check']:<16} prompt={u['prompt']} completion={u['completion']} total={u['total']}")
    print(f"  {'TOTAL':<16} {report['total_tokens']}")

    out = ROOT / "runs" / "day1_api_check.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport: {out}")


if __name__ == "__main__":
    main()
