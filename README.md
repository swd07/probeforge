# ProbeForge

AI agent that diagnoses faults in an industrial relay-contactor circuit (star-delta reversing motor starter) by choosing its own virtual measurements, under hard safety limits enforced in code. Built for the Meta Global AI Developer Hackathon 2026.

Status: Day 2. Circuit simulator, fault catalog and schematic generator are done and tested. The agent, policy layer and UI are not built yet.

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
