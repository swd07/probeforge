# ProbeForge

AI agent that diagnoses faults in an industrial relay-contactor circuit (star-delta reversing motor starter) by choosing its own virtual measurements, under hard safety limits enforced in code. Built for the Meta Global AI Developer Hackathon 2026.

Status: Day 1, project setup and Meta Model API checks. The simulator, agent and UI are not built yet.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```
uv sync
```

Create `.env` in the project root:

```
META_API_KEY=your_key_here
```

## Meta Model API check

```
uv run python scripts/check_meta_api.py
```

Runs four checks against Muse Spark (`muse-spark-1.3`, base URL `https://api.meta.ai/v1`, OpenAI-compatible Chat Completions):

| Check | What it verifies |
|---|---|
| tools | One fake `measure_voltage` tool, parallel tool calls, full round trip with tool results |
| stream | Same tool with streaming, tool-call arguments rebuilt from deltas |
| structured | JSON schema output (`strict: true`) for a hypothesis list |
| image | A generated relay schematic PNG; the model lists components, terminals and wire numbers, scored against ground truth |

Token usage is printed per call. A JSON report and the schematic image are written to `runs/` (git-ignored).

Options: `--model`, `--effort minimal|low|medium|high|xhigh`, `--only tools stream structured image`.
