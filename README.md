# ProbeForge

AI agent that diagnoses faults in an industrial relay-contactor circuit (star-delta reversing motor starter) by choosing its own virtual measurements, under hard safety limits enforced in code. Built for the Meta Global AI Developer Hackathon 2026.

Status: Day 4. Simulator, faults, tools, safety policy, Muse Spark agent, half-split baseline and evaluation harness are done and tested. The web UI is next.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```
uv sync
```

Create `.env` in the project root:

```
META_API_KEY=your_key_here
```

## Circuit and simulator

![Star-delta reversing starter](docs/star_delta_reversing.svg)

The circuit is a star-delta motor starter with forward / reverse, defined once in [scenarios/circuits/star_delta_reversing.yaml](scenarios/circuits/star_delta_reversing.yaml). The same file drives the simulator, the text netlist for the agent (`Netlist.to_text()`) and the schematic above (`uv run python scripts/render_schematic.py`; a test fails if the committed SVG is out of date).

The simulator (`src/probeforge/sim/`) is pure Python and deterministic:

- Closed contacts merge nets; coils pick up when their terminals see different phases; contactor states iterate until stable. Mechanical interlocks KM1/KM2 and KM3/KM4.
- Short circuits blow the first protection device that clears them (FU1, FU2, then QF1).
- On-delay timer KT and thermal overload KK1 advance in 0.1 s ticks.
- Motor state: stopped, star / delta, forward / reverse, or humming on phase loss, with per-line current (zero / nominal / overcurrent).
- Measurements use nodal analysis over the same model, so a voltmeter across an open contact reads 230 V and an ohmmeter sees parallel paths through coils and lamps, like on a real panel.

```python
from probeforge.sim import Circuit
from probeforge.faults import Fault

c = Circuit.load("scenarios/circuits/star_delta_reversing.yaml")
c.apply_fault(Fault("KM1", "stuck_open", "13-14"))   # hidden from the agent
c.set_power(True)
c.press("Start Fwd")
c.indicators()             # {'lamps': {...}, 'motor': 'stopped', 'phase_currents': {...}}
c.voltage("KM1:13", "KM1:14")   # 230.0
c.set_power(False)
c.resistance("KM1:A1", "KM1:A2")  # 550.0
```

Faults (`src/probeforge/faults/`): the 8 hand-written scenarios live in `scenarios/s0*.yaml`. `all_faults()` enumerates every part in every failure mode (91 faults); `random_fault(netlist, seed, visible_only=True)` picks unseen holdout faults. About 15 of the 91 are latent (no visible symptom during normal operation), which `has_visible_symptom()` detects.

## Tools, safety policy, agent

- **Tools** (`src/probeforge/tools/`): `read_indicators`, `press_button` (with `hold_seconds`), `wait`, `set_power`, `measure_voltage`, `measure_resistance`, `get_schematic`, `update_hypotheses`, `perform_action`, `submit_diagnosis`. Every call gets a step number, goes through the policy and is logged. Outputs only contain what a technician at the panel could observe; a test drives every tool on all 91 faults and checks that no output, log or prompt names the fault.
- **Baseline** (`src/probeforge/baseline/`): deterministic. Runs a fixed functional test mirrored on a fault-free twin, half-splits the supply path of the first load whose voltage is missing, refines with fixed rules, and falls back to an exhaustive resistance comparison.
- **Policy** (`src/probeforge/policy/`): voltage only with power on, resistance only with power off, at most 3 consecutive Start presses, power-on after a protection trip and protection resets need human approval (auto-denied in batch runs), bypass / modify / replace / jumper are always blocked, a diagnosis must cite executed observation steps. Blocked calls come back to the agent as errors and are counted.
- **Agent** (`src/probeforge/agent/`): Muse Spark (`muse-spark-1.3`) with native tool calling. It gets the panel state, the schematic as PNG (rendered from the SVG with resvg) plus the text netlist, the tools and the policy summary. It must call `update_hypotheses` after every measurement (in the same turn as the next measurements; up to 3 measurements per turn), the image is sent only with the first request, text replies without a tool call get a short nudge, tool calls the model writes as text markup are recovered, it is warned 5 and 2 turns before the 30-turn cap, and `insufficient_information` is a valid outcome. Evidence items in a diagnosis are typed `functional_test` or `instrument_reading`.

```
uv run python scripts/run_scenarios.py --effort low      # all 8 scenarios, prints a results table
```

Each run writes `runs/<timestamp>_<effort>/<scenario>.json` (tool calls, results, hypotheses, tokens, latency per turn; no fault inside) plus `results.md` / `results.json` with the score.

## Results

Full tables and a failure analysis of every wrong answer: [docs/results/2026-10-27_comparison.md](docs/results/2026-10-27_comparison.md).

| | Holdout visible (30) | Latent (10) | Confidently wrong | Meas per case | Cost per case |
|---|---|---|---|---|---|
| Agent (muse-spark-1.3, low) | 25/30 (28/30 incl. justified) | 10/10 | 1 | 6.9 | $0.09 |
| Half-split baseline | 22/30 (24/30) | 10/10 | 4 | 10.3 | free |

Holdout = 30 random visible + 10 random latent faults (seed 2026), none of the 8 hand-written scenarios. "Justified" = the true fault is
observationally identical to another fault (checked by simulation) and the answer was insufficient_information or that twin. On the
8 hand-written scenarios run 3 times, the agent solved 22/24 (s06 is the weak spot) and the baseline 8/8.

```
uv run python scripts/run_scenarios.py --suite holdout --effort low --workers 8
uv run python scripts/run_scenarios.py --runner baseline --suite all
uv run python scripts/run_scenarios.py --repeat 3 --effort low
```

## Tests

```
uv run pytest
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
