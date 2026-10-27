# ProbeForge

AI agent that diagnoses faults in an industrial relay-contactor circuit by choosing its own virtual measurements, under hard safety limits enforced in code. Built for the Meta Global AI Developer Hackathon 2026 (Indie Developer track, theme "Push the Frontier").

## Hard facts

- Solo project. Author: Eduard Kharaev (GitHub: swd07).
- Submission deadline: Nov 4, 2026, 9:00 PM ET (Nov 5, 06:00 Tbilisi). Need: public GitHub repo, working software, demo video (about 3 minutes).
- Only work done during the event counts. Do not copy code from the author's other projects.
- Judging (equal weight): Impact, Use of Meta AI tooling, Technical depth and execution, Demo. Indie track: "creativity, technical ambition, and whether it works".
- Discouraged formats: Streamlit apps, dashboards as the main feature, basic RAG, chatbot wrappers. Do not build any of these.
- Budget: $150 Meta Model API credit. Not a binding constraint, but log token usage per run.

## Writing style rule

Never use the em dash character in any text (README, UI, comments, commit messages). Use commas, colons, periods or parentheses.

## The core idea

A star-delta motor starter with reversing (forward / reverse) is simulated in software. A hidden fault is injected. The agent sees only external symptoms (indicator lamps, motor behaviour) and must find the root cause by calling measurement tools, step by step, like a field electrician:

OBSERVE (symptoms) -> REASON (hypotheses) -> ACT (pick next measurement) -> MEASURE (simulator answers) -> ADAPT (update hypotheses) -> DIAGNOSE (with confidence and evidence).

The agent never sees the injected fault, never edits the circuit, and every action passes through a policy layer that blocks unsafe actions. This is "shadow mode": the agent diagnoses and proposes, a human approves anything risky.

Results are compared against (a) a simple deterministic baseline and (b) the measurement sequence a real engineer would use for the same scenario.

## Architecture

```
probeforge/
  sim/          circuit model and simulator (pure Python, no ngspice)
  faults/       fault definitions and injector
  tools/        measurement tool API exposed to the agent
  policy/       safety policy engine (allow / block / require human approval)
  agent/        Muse Spark planner loop with tool calling
  baseline/     deterministic baseline diagnostician (half-split search)
  eval/         batch runner, metrics, engineer reference traces
  web/          UI: live schematic, measurement highlights, agent reasoning log
  scenarios/    YAML scenario files (fault + expected symptoms + engineer trace)
```

### 1. Simulator (sim/)

- Model the circuit as a graph: nodes = terminals (e.g. X1:1, KM1:A1), edges = components (fuse, NC/NO contacts, coils, buttons, thermal relay contact, timer contact, motor windings, lamps).
- Control circuit: compute energized nodes by propagation from L to N through closed contacts. Coils energize when they have a path; their contacts change state; iterate until stable. Timer relay KT switches after a configurable delay (simulated time steps).
- Power circuit: simplified three-phase model. Report per-phase current as nominal / zero / overcurrent, and motor state: stopped, star, delta, humming (phase loss), reverse.
- Mechanical interlocks between forward/reverse and star/delta contactors.
- Must be deterministic and fast (thousands of runs per minute) so evaluation is cheap.
- Expose a clean API: `Circuit.load(yaml)`, `apply_fault(f)`, `press(button)`, `set_power(on/off)`, `step(dt)`, `voltage(a, b)`, `resistance(a, b)`, `indicators()`.

### 2. Faults (faults/)

Initial scenario set (agent must handle all; pairs 1/2 and 4/5 have similar symptoms on purpose):

| # | Hidden fault | External symptom |
|---|---|---|
| 1 | Control fuse FU blown | Nothing responds, "Power" lamp off |
| 2 | Stop button NC contact stuck open | Nothing responds, "Power" lamp on |
| 3 | Thermal overload relay tripped | "Fault" lamp on, no start |
| 4 | Forward contactor KM1 coil open | Forward does not start, reverse works |
| 5 | KM1 self-hold auxiliary contact not closing | Motor runs only while Start is held |
| 6 | Timer relay KT failed | Motor stays in star |
| 7 | Star contactor contact welded | Interlock blocks delta |
| 8 | Phase loss in power circuit | Motor hums, thermal relay trips |

Add a random fault generator (any component, any failure mode: open, short, stuck, welded) for holdout tests that nobody hand-picked.

### 3. Tools exposed to the agent (tools/)

- `read_indicators()` -> lamp states and motor state
- `press_button(name)` -> Start Fwd, Start Rev, Stop
- `set_power(on|off)`
- `measure_voltage(point_a, point_b)` -> volts
- `measure_resistance(point_a, point_b)` -> ohms or "open"
- `get_schematic()` -> terminal list and component list (text netlist); the schematic image is also sent to the model
- `submit_diagnosis(component, failure_mode, confidence, evidence[])`

Every call returns a result and is logged with a step number.

### 4. Safety policy (policy/)

Enforced in code, never only in the prompt.

| Action | Allowed | Condition |
|---|---|---|
| Read indicators | Yes | Always |
| Measure voltage | Yes | Power on |
| Measure resistance / continuity | Yes | Power off only (otherwise blocked) |
| Press Start / Stop | Yes | Max N consecutive start attempts |
| Re-apply power after a protection trip | Needs human approval | Agent must request it with a reason |
| Bypass interlock, modify circuit, replace part | Never | Blocked |
| Submit diagnosis | Yes | Must include confidence and supporting measurements |

Blocked attempts are returned to the agent as an error and counted as a metric.

### 5. Agent (agent/)

- Model: Muse Spark 1.3 via the Meta Model API (OpenAI-compatible endpoint, base URL and exact model id must be checked in https://dev.meta.ai/docs before coding; read the key from env `META_API_KEY`).
- Native tool calling and JSON structured output. Keep an explicit hypothesis list (component, failure mode, probability) in the agent state and update it after every measurement.
- Input: symptoms, schematic image plus text netlist, tool list, policy summary.
- Stop conditions: diagnosis submitted, max steps reached, or agent declares "insufficient information" (allowed and better than a wrong guess).
- Optional second mode: Muse Wonder for hard cases, compare cost vs accuracy.

### 6. Baseline (baseline/)

Deterministic half-split search along the control circuit path from L to N using voltage measurements, plus fixed rules for the power circuit. The agent must beat it on number of measurements or on accuracy for the hard pairs, otherwise report honestly.

### 7. Evaluation (eval/)

Metrics per run: correct component (yes/no), correct failure mode (yes/no), measurements to diagnosis, policy violations attempted, tokens and cost, wall time.

Compare three columns: Agent, Baseline, Engineer reference trace (from scenarios/*.yaml, filled in by a real electrical engineer).

Output: a results table (markdown + JSON) generated by a script, used in the README and the demo.

### 8. Web UI (web/)

Not a dashboard. One main screen:
- Schematic drawn as SVG, with the probe points the agent measures lighting up live.
- Right panel: agent reasoning steps, hypothesis list with probabilities changing after each measurement.
- Blocked actions flash red with the policy reason.
- "Inject random fault" button so a judge can test unseen faults live.
- Stack: FastAPI backend with WebSocket streaming, simple frontend (Vite + React or plain TS). No Streamlit.

## Day 1 checks (before building the rest)

1. Meta API key works; confirm base URL and model id.
2. Muse Spark tool calling: one fake tool, parallel calls, streamed arguments.
3. Structured output with a JSON schema.
4. Image input: send a relay schematic image, ask it to list terminals and contacts. If it reads it poorly, use the text netlist as the source of truth and keep the image for display only.

Kill rule: if by end of Oct 29 the agent cannot correctly diagnose at least 5 of the 8 scenarios, simplify the circuit before adding anything else.

## Plan

- Oct 28: repo setup, Day 1 API checks, simulator core (control circuit propagation), scenario YAML format.
- Oct 29: power circuit, timer, interlocks, all 8 faults, tool API, policy engine with tests.
- Oct 30: agent loop with tool calling and hypothesis tracking; run on all 8 scenarios.
- Oct 31: baseline, eval harness, random fault generator, first results table.
- Nov 1: web UI with live schematic and reasoning panel.
- Nov 2: engineer reference traces into scenarios, prompt and loop tuning, holdout run.
- Nov 3: README, architecture diagram, results, polish, record demo.
- Nov 4: buffer, final video, submit well before 9 PM ET.

## Engineering rules

- Python 3.11+, managed with uv. Tests with pytest. Simulator and policy must have unit tests.
- The agent must never receive the injected fault through any channel (prompt, logs, tool output). Add a test that checks this.
- No hardcoded or prerecorded agent outputs anywhere in the demo path.
- Commit small and often with clear messages.
