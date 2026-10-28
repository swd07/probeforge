# ProbeForge

AI agent that diagnoses faults in an industrial relay-contactor circuit (star-delta reversing motor starter) by choosing its own virtual measurements, under hard safety limits enforced in code. Built for the Meta Global AI Developer Hackathon 2026.

Status: Day 4. Simulator, faults, tools, safety policy, Muse Spark agent, baselines, evaluation harness (clean holdout results), the live web UI and phase 1 of the hybrid pipeline (Muse Spark reads the schematic, a planner measures, Muse Spark repairs the netlist and explains) are done and tested.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```
uv sync
```

Create `.env` in the project root:

```
META_API_KEY=your_key_here
```

## Live web UI

![Agent at work](docs/screenshots/w1920_2_midrun.png)

One screen showing the agent working, streamed step by step over a WebSocket from FastAPI to a Vite + React + TypeScript frontend:

- **Front panel** (top): lamps, push buttons (they light up when the agent presses them), main breaker, motor (spins in star / delta, shakes when humming) and clamp-meter line currents.
- **Schematic** (center): the same SVG generated from the netlist. Every probe point the agent measures lights up with the reading next to it; nets the agent measured turn red (live) or blue (dead). The true live wiring is only shown after the run, because colouring it during the run would give the fault away. Mouse wheel zooms, drag pans, Fit shows the whole drawing; in agent mode "follow probes" zooms to each new measurement and the view zooms out at the reveal.
- **Right panel**: hypothesis bars that move after each measurement, and the reasoning feed: the model's short notes, every tool call with its result, policy blocks in red, approval requests in amber.
- **Approval card**: when the agent asks to reset a protection device or re-apply power after a trip, the run pauses until a human clicks Approve or Deny.
- **Top bar**: "Random fault (any of 91)" or "Clean test fault (from holdout_clean.yaml)" picks a fault on the server and the browser does not learn which one until the end; or pick one of the 8 scenarios by its symptom. After a run the choice resets, and the result card says which fault and pool were actually run.
- **Result card** (docked over the right panel, collapsible): the injected fault, the verdict (correct / justified / pole open / wrong, pole level), measurements, tokens, cost and time, and the decisive measurement: the reading that raised the winning hypothesis the most, shown next to what a healthy panel reads at the same point (the logged actions replayed on a fault-free circuit).

| Approval card | Result and reveal |
|---|---|
| ![Approval](docs/screenshots/qf1_approval_card.png) | ![Result](docs/screenshots/w1920_8_result.png) |

**Engineer mode** (same screen, a human instead of the agent): click two terminals or wires on the schematic to place the
meter probes and measure volts or ohms, press the panel buttons, switch the breaker, wait, request a protection reset,
then submit a diagnosis from a form (component, part, failure mode, confidence, and evidence picked from your own steps).
Every action goes through the same tools and safety policy as the agent, so a resistance reading on a live circuit is
blocked with the same red flash. The trace is saved in the agent trace format to `scenarios/engineer_traces/` and becomes
the engineer reference column. **Compare** then runs the baseline and the agent on the same fault and shows engineer,
agent and baseline side by side: verdict, measurements, redundant readings, blocked attempts, time, cost and the full
sequence of meter readings.

| Engineer mode: blocked reading | Engineer vs agent vs baseline |
|---|---|
| ![Blocked](docs/screenshots/manual_2_blocked.png) | ![Compare](docs/screenshots/manual_6_compare.png) |

**Hybrid mode** (third button in the top bar): Muse Spark reads the schematic image into a netlist (a live read, or
a saved real read with known errors, from the PNG or from a phone photo), the regions it flagged as uncertain light up on the schematic for a human to
confirm, then the information-gain planner measures. When a reading contradicts every candidate fault, the feed shows
the inconsistent reading in red, Muse Spark rechecks the drawing and the correction appears as a diff before the
planner continues; a proposal that would change fault-free behaviour no reading contradicted is shown as rejected.
If the answer depends on a flagged region (for example which KM3 pole feeds which winding), the UI asks the human
which wiring the panel has; without an answer the pole is reported as ambiguous. The result card carries Muse
Spark's explanation for the technician. See
[Hybrid pipeline](#hybrid-pipeline-phase-1).

| Flagged regions for human confirmation | Netlist correction during the run |
|---|---|
| ![Flags](docs/screenshots/hybrid_live_flags.png) | ![Correction](docs/screenshots/hybrid_km4_2_correction.png) |
| **Wiring question: the answer depends on a flagged region** | **After the technician picked the real wiring** |
| ![Wiring](docs/screenshots/hybrid_photo_wiring_wiring.png) | ![Result](docs/screenshots/hybrid_photo_wiring_8_result.png) |

The UI replaces em dashes in the model's text with commas for display; the content is not otherwise changed.

Run it:

```
cd web && npm install && npm run build && cd ..
uv run python -m probeforge.server          # http://127.0.0.1:8000
```

For frontend development run `npm run dev` in `web/` (Vite on :5173, proxied to the backend on :8000).
`scripts/screenshot_ui.py` drives a full live run in headless Edge with Playwright and saves screenshots to `docs/screenshots/`.
For reproducible demos `?fault=QF1:5-6%20open` in the URL injects a specific fault (shown as "fault chosen by URL"; the UI itself never offers this).

## Circuit and simulator

![Star-delta reversing starter](docs/star_delta_reversing.svg)

The circuit is a star-delta motor starter with forward / reverse, defined once in [scenarios/circuits/star_delta_reversing.yaml](scenarios/circuits/star_delta_reversing.yaml). The same file drives the simulator, the text netlist for the agent (`Netlist.to_text()`) and the schematic above (`uv run python scripts/render_schematic.py`; a test fails if the committed SVG is out of date).

The simulator (`src/probeforge/sim/`) is pure Python and deterministic:

- Closed contacts merge nets; coils pick up when their terminals see different phases; contactor states iterate until stable. Mechanical interlocks KM1/KM2 and KM3/KM4 (drawn with the IEC symbol: a dashed linkage with an inverted triangle).
- Short circuits blow the first protection device that clears them (FU1, FU2, then QF1).
- On-delay timer KT and thermal overload KK1 advance in 0.1 s ticks.
- Motor state from the winding currents (nodal analysis, positive and negative sequence components): stopped, star / delta, forward / reverse, unbalanced, or humming (stalled, locked-rotor current). Line currents in amps (clamp meter, 10 A rated in delta) plus zero / nominal / overcurrent.
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

Faults (`src/probeforge/faults/`): the 8 hand-written scenarios live in `scenarios/s0*.yaml`. `all_faults()` enumerates every part in every failure mode (91 faults); `random_fault(netlist, seed, visible_only=True)` picks unseen holdout faults. 15 of the 91 are latent (no visible symptom during normal operation), which `has_visible_symptom()` detects.

## Tools, safety policy, agent

- **Tools** (`src/probeforge/tools/`): `read_indicators`, `press_button` (with `hold_seconds`), `wait`, `set_power`, `measure_voltage`, `measure_resistance`, `get_schematic`, `update_hypotheses`, `perform_action`, `submit_diagnosis`. Every call gets a step number, goes through the policy and is logged. Outputs only contain what a technician at the panel could observe; a test drives every tool on all 91 faults and checks that no output, log or prompt names the fault.
- **Baseline** (`src/probeforge/baseline/`): deterministic. Runs a fixed functional test mirrored on a fault-free twin, half-splits the supply path of the first load whose voltage is missing, refines with fixed rules, and falls back to an exhaustive resistance comparison.
- **Policy** (`src/probeforge/policy/`): voltage only with power on, resistance only with power off, at most 3 consecutive Start presses, power-on after a protection trip and protection resets need human approval (auto-denied in batch runs), bypass / modify / replace / jumper are always blocked, a diagnosis must cite executed observation steps. Blocked calls come back to the agent as errors and are counted.
- **Agent** (`src/probeforge/agent/`): Muse Spark (`muse-spark-1.3`) with native tool calling. It gets the panel state, the schematic as PNG (rendered from the SVG with resvg) plus the text netlist, the tools and the policy summary. It must call `update_hypotheses` after every measurement (in the same turn as the next measurements; up to 3 measurements per turn; skipping it is not blocked but counted as `missing_hypothesis_updates`), the image is sent only with the first request, text replies without a tool call get a short nudge, tool calls the model writes as text markup are recovered, it is warned 5 and 2 turns before the 30-turn cap, and `insufficient_information` is a valid outcome. Evidence items in a diagnosis are typed `functional_test` or `instrument_reading`.

```
uv run python scripts/run_scenarios.py --effort low      # all 8 scenarios, prints a results table
```

Each run writes `runs/<timestamp>_<effort>/<scenario>.json` (tool calls, results, hypotheses, tokens, latency per turn; no fault inside) plus `results.md` / `results.json` with the score.

## Results (clean holdout)

Full report with failure analysis: [docs/results/2026-10-27_clean.md](docs/results/2026-10-27_clean.md).

The clean holdout is every fault never used during development: 91 possible single faults minus the 8 hand-written
scenarios minus the 40 dev holdout faults = 43 faults (38 visible, 5 latent), listed in
[scenarios/holdout_clean.yaml](scenarios/holdout_clean.yaml). The agent prompt and the baseline rules were frozen before
the run. Agent: `muse-spark-1.3`, reasoning effort low, approval requests denied.

"Correct" is pole level: component, failure mode and part (pole or contact) must all match. The component-level
score (part ignored) is kept as a column. Every run was rescored from its saved diagnosis:
[docs/results/2026-10-28_pole_level.md](docs/results/2026-10-28_pole_level.md).

| | Visible correct (pole) | incl. justified | Component level | Latent | Confidently wrong | Meas per case | Cost per case |
|---|---|---|---|---|---|---|---|
| Agent | **30/38** | **33/38** | 30/38 | 5/5 | **4** | **8.3** | $0.068 |
| Half-split baseline | 25/38 | 25/38 | 25/38 | 5/5 | 9 | 11.0 | free |
| Information-gain baseline (perfect fault model, see note) | 35/38 | 38/38 | 35/38 | 5/5 | 0 | 2.6 | free |

The information-gain baseline simulates all 91 candidate faults in lock step with the panel and always takes the
reading that splits the survivors best. It needs a complete, exact fault model of this very circuit, which the agent
does not have, so it is a ceiling for measurement choice with perfect knowledge, not a peer. The agent sits between
the rule-based half-split and that ceiling. Details: [docs/results/2026-10-28_review.md](docs/results/2026-10-28_review.md).

- **Input ablation** ([docs/results/2026-10-28_input_ablation.md](docs/results/2026-10-28_input_ablation.md)): netlist
  only 30/38, schematic image only (no netlist) 28/38 at pole level (31/38 component level: three answers left the
  pole open), both 30/38. Within run-to-run noise. (The image-only run predates a prompt fix: it still said nominal
  values are in the netlist; image-only mode now says unlabeled values must be inferred or measured.)
- **Schematic transcription:** Muse Spark turns the PNG into our YAML netlist with all 17 components and 51 parts right
  and the whole control circuit exact; the errors are at the power-circuit wire crossovers (28 to 29 of 35 nets exact).
- **Calibration** ([docs/results/2026-10-28_calibration.md](docs/results/2026-10-28_calibration.md), pole level): 94%
  of diagnoses are stated at 90%+ confidence and are right 92% of the time over all runs (89% on the clean holdout);
  the few stated below 90% are overconfident (3 of 17 right).

"Justified": the true fault gives exactly the same readings as another fault in every state the tools can reach (checked
by simulation) and the answer was insufficient_information or that twin. Single run per case; reruns show individual cases
flip between runs. Known weak spots: welded L1/L3 main poles that cause a fuse-blowing short (the agent tends to blame the
blown fuse), and "voltage present is not coil intact" (dev scenario s06 fails 2 of 3). Everything before the clean run is in
[docs/results/dev/](docs/results/dev/), labelled dev because the prompt and baseline were tuned with those faults visible.

## Hybrid pipeline (phase 1)

Report: [docs/results/2026-10-28_hybrid.md](docs/results/2026-10-28_hybrid.md). Code: `src/probeforge/hybrid/`.

1. **Read:** Muse Spark transcribes the schematic image into the YAML netlist format (given the format spec, never the
   answer) and lists uncertain regions. The UI asks a human to confirm them; batch runs accept the transcription.
2. **Model:** the fault catalog is generated from the transcribed netlist (every part in every failure mode). Values
   the drawing does not print are unknowns: timer delay and trip time become candidate dimensions on a log grid,
   and without a motor rating line currents are compared as zero / nominal / overcurrent only.
3. **Plan:** the information-gain planner simulates the transcribed netlist and picks readings; the readings come from
   the real circuit through the same tools and safety policy as the agent.
4. **Verify:** a reading that no candidate explains stops the planner. Muse Spark gets the image, the netlist, the
   readings and the candidates and proposes a correction (logged as a diff); the planner rebuilds, replays every
   reading and continues, or hands over to a human after 3 failed corrections.
5. **Explain:** Muse Spark writes a short explanation for the technician citing the decisive readings.

Evaluated on the clean holdout starting from a real transcription with 6 of 35 nets wrong
([scenarios/transcriptions/star_delta_run2.yaml](scenarios/transcriptions/star_delta_run2.yaml)):

| | Visible correct (pole) | incl. justified | Component level | Latent | Confidently wrong | Meas per case | Cost per case |
|---|---|---|---|---|---|---|---|
| Pure agent (true netlist + image) | 30/38 | 33/38 | 30/38 | 5/5 | 4 | 8.3 | $0.068 |
| Info-gain on the true netlist | 35/38 | 38/38 | 35/38 | 5/5 | 0 | 2.6 | free |
| **Hybrid (flawed transcription + repair)** | **25/38** | **28/38** | 29/38 | 5/5 | **2** | **3.2** | $0.066 |
| Hybrid without repair | 10/38 | 13/38 | 10/38 | 5/5 | 0 | 1.4 | free |

The wrong wiring contradicted the readings in 31 of 43 cases. Muse Spark proposed 35 corrections: 32 made the model
consistent with every reading again and 29 made the healthy machine behave right, but none restored the exact true
netlist (pin permutations a healthy panel cannot show remain). At component level no correction led to a wrong
diagnosis, but at pole level two KM3 star-pole faults were named with the wrong pole at full confidence: the leftover
permutation maps the poles to the wrong windings and no reading contradicts it. A real phone photo of the schematic
reads as well as the PNG ([docs/results/2026-10-28_photo.md](docs/results/2026-10-28_photo.md)).

### Changes after seeing the clean holdout (dev)

Report: [docs/results/2026-10-28_dev_changes.md](docs/results/2026-10-28_dev_changes.md). Because these were made
after the clean results were seen, the hybrid numbers below are dev results; the final unseen test will be a second
circuit.

- **Wiring check of flagged regions:** if a terminal of the diagnosed part is in a region the transcription flagged,
  the alternative wirings of that region are replayed against every reading. If one that fits implies another pole,
  the pole is not reported ("pole ambiguous: confirm wiring at ..."), confidence drops, and the UI asks a human which
  wiring the panel has.
- **Correction acceptance rule:** a repair proposal that changes fault-free behaviour no reading contradicted is
  rejected and logged, and Muse Spark is asked again with the reasons.
- **Mechanical interlock symbol** in the drawing (it was missing, so no transcription could find the interlocks;
  with it, 3 of 3 transcriptions list both).

| Dev, pole level | Visible correct (pole) | incl. justified | Component level | Confidently wrong | Pole left open | Meas per case | Cost per case |
|---|---|---|---|---|---|---|---|
| Hybrid, PNG run 2 transcription | 26/38 | 29/38 | 30/38 | 3 | 2 | 2.9 | $0.065 |
| Hybrid, phone photo transcription (best) | 20/38 | 23/38 | 31/38 | 2 | 11 | 3.0 | $0.026 |
| Hybrid, phone photo transcription (worst) | 20/38 | 23/38 | 31/38 | 4 | 9 | 3.0 | $0.024 |

All 10 rejected proposals would have broken the fault-free machine (checked against the truth afterwards). The
wiring check turns wrong poles into "pole ambiguous" where the flags cover the wiring, and also drops poles that had
been right only by luck. It cannot help where the transcription did not flag the wiring (worst photo read: KM3 star
poles still wrong). A side effect: when a bad proposal for a welded main pole is rejected, the next one can pass the
rule and explain the readings with an open pole (c15, c18), so confidently wrong did not go down overall.

```
uv run python scripts/run_scenarios.py --suite clean --effort low --workers 8      # agent, clean holdout
uv run python scripts/run_scenarios.py --runner baseline --suite clean             # half-split baseline
uv run python scripts/run_scenarios.py --runner infogain --suite clean             # information-gain baseline
uv run python scripts/run_scenarios.py --suite clean --no-image --effort low       # netlist only
uv run python scripts/run_scenarios.py --suite clean --no-netlist --effort low     # schematic image only
uv run python scripts/run_scenarios.py --runner hybrid --suite clean               # hybrid pipeline (run-2 transcription), labelled dev
uv run python scripts/run_scenarios.py --runner hybrid --suite clean --transcription scenarios/transcriptions/star_delta_photo_run3.yaml --image scenarios/photos/star_delta_phone.jpg   # from the phone photo
uv run python scripts/run_scenarios.py --runner hybrid --suite clean --no-repair --no-explain   # without Verify
uv run python scripts/transcribe_schematic.py --runs 3                             # Read step, scored against the truth
uv run python scripts/summarize_results.py OUT.md "Label=runs/<dir>" ...           # pole-level table from saved runs
uv run python scripts/calibration.py                                               # confidence calibration
uv run python scripts/run_scenarios.py --suite scenarios --repeat 3 --effort low   # dev scenarios, variance
uv run python scripts/run_scenarios.py --suite clean --only c02 --approve          # simulated human approves
```

## Spend guard

Every agent run records its API cost in `runs/spend.json` (started at the $21 spent before the ledger existed).
`run_scenarios.py` estimates a batch at $0.10 per agent run and refuses to start if the total would pass $110, unless
`--force`. The UI refuses agent, hybrid and compare runs over the limit. Hybrid runs record their transcription,
repair and explanation calls. Spend so far: $43.62.

## Known Muse Spark behaviour: tool calls written as text

With native tool calling on (`tools=[...]`, `tool_choice` auto), `muse-spark-1.3` sometimes answers with no `tool_calls` and
the call written into the message text instead, in an internal markup:

```
<atem:function_calls>
<atem:invoke name="default.submit_diagnosis">
<atem:parameter name="confidence">0.95</atem:parameter>
<atem:parameter name="component">KK1</atem:parameter>
<atem:parameter name="evidence">[{"step": 0, "type": "functional_test", "observation": "..."}]</atem:parameter>
...
</atem:invoke>
</atem:function_calls>
```

We saw it mostly for `submit_diagnosis` (the largest schema, with a nested evidence array). A plain "call the tool" nudge
does not help: the model repeats the same text until the turn limit. The agent loop therefore parses this markup
(`recover_text_tool_calls` in `src/probeforge/agent/loop.py`), turns it into a native tool call in the history (so the
API's rule that every tool call is followed by its tool result still holds) and runs it. Every run counts these as
`recovered_text_calls`; the results tables show the total.

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
