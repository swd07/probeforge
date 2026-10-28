# ProbeForge architecture

ProbeForge diagnoses hidden faults in a simulated star-delta reversing motor starter by choosing its own
measurements, like a field electrician, under a safety policy enforced in code. It has three ways to diagnose
the same panel, sharing one simulator, one tool API and one safety policy:

- **Hybrid pipeline** (the main mode): Muse Spark reads the schematic (a phone photo or a rendered drawing), a
  deterministic information-gain planner chooses the measurements, Muse Spark explains the result.
- **Pure agent**: Muse Spark runs the whole diagnosis itself with tool calls.
- **Engineer mode**: a human drives the same tools in the UI; the trace is the engineer reference.

Decisions behind this design and the evidence for them are in [DECISIONS.md](DECISIONS.md).

## Code map

| Path | What it holds |
|---|---|
| `src/probeforge/sim/` | Netlist loader, circuit simulator (relay logic, timer, thermal relay, interlocks, protection, nodal analysis for volts, ohms and motor currents), schematic renderer (SVG/PNG from the netlist) |
| `src/probeforge/faults/` | Fault model, `all_faults()` (every part in every failure mode: 91 faults), random and latent-fault helpers |
| `src/probeforge/tools/toolbox.py` | The tool API (`read_indicators`, `press_button`, `wait`, `set_power`, `measure_voltage`, `measure_resistance`, `perform_action`, `submit_diagnosis`, ...); every call is logged with a step number |
| `src/probeforge/policy/engine.py` | Safety policy, checked before every tool call |
| `src/probeforge/agent/` | Pure agent: Meta Model API client, frozen prompt, tool-calling loop |
| `src/probeforge/baseline/` | Half-split baseline; information-gain planner (the hybrid's planner, also a baseline on the true netlist) |
| `src/probeforge/hybrid/` | Read (transcription, consensus), wiring variants and check, repair with acceptance rule, explanation, pipeline |
| `src/probeforge/eval/` | Scoring (pole level), observational twins, traces, engineer reference, spend ledger |
| `src/probeforge/server/` + `web/` | FastAPI + WebSocket backend, React UI (schematic, panel, feed, hypotheses, result card) |
| `scripts/` | Batch runner, summaries, calibration, transcription and consensus tests, screenshots |
| `scenarios/` | Circuit YAML, 8 hand-written scenarios, dev and clean holdout lists, saved transcriptions, the phone photo |

## Hybrid pipeline: data flow

```
 schematic image (phone photo JPEG or rendered PNG)
        |
        v
 1. READ        Muse Spark transcribes it 3 times (medium effort), each read with its own "uncertain" list
        |       consensus.py: the read that agrees most with the others becomes the MODEL netlist;
        |       terminals whose connections differ between reads become extra uncertain regions
        v
 model netlist + flags (Muse Spark's own + disagreement regions)   [UI: a human confirms the flagged regions]
        |
        v
 2. MODEL       fault catalog generated from the model netlist (every part x failure mode);
        |       unprinted values (timer delay, trip time) become candidate grids; without a motor rating
        |       line currents are compared as zero / nominal / overcurrent only
        v
 3. PLAN        information-gain planner over joint hypotheses (fault x unknown parameters x wiring variant)
        |       - wiring variants: alternative wirings of the flagged regions (one side of same-kind parts of
        |         a component in any order), kept only while they reproduce every reading
        |       - each step takes the reading that leaves the fewest distinct faults expected
        |       - readings come from the TRUE circuit through the ToolBox and the safety policy
        |       - variants around the leading component are added before any power-off decision; readings
        |         across a part's own terminals (also stop, then start held) separate them
        v
 4. VERIFY      a reading no candidate explains:
        |       a) first, alternative wirings of every flagged region (no model call)
        |       b) else Muse Spark proposes a corrected netlist (medium effort, image + readings + candidates);
        |          rejected if it rewires terminals outside the flagged regions without naming a new region,
        |          or if it changes fault-free behaviour no reading contradicted (acceptance.py);
        |          after 2 rejections no more proposals; accepted ones rebuild the planner and replay every reading
        |       c) else hand over to a human (insufficient_information)
        v
 diagnosis: a specific pole only if one fault remains under every wiring that fits the readings;
        |   otherwise "pole ambiguous: confirm wiring at ..." (UI: a human picks the wiring the panel has)
        v
 5. EXPLAIN     Muse Spark writes a short explanation for the technician citing the decisive steps (low effort)
```

The planner never sees the injected fault or the true netlist: it only gets the model netlist, the flags and
the tool results. The true netlist is used after each repair answer, for the evaluation log only.

## Pure agent

Muse Spark (`muse-spark-1.3`, reasoning effort low) gets the symptoms, the text netlist and the schematic image
(either can be ablated), the tool list and the policy summary. It keeps an explicit hypothesis list with
probabilities (`update_hypotheses`), picks measurements with native tool calling, and ends with
`submit_diagnosis` (component, part, failure mode, confidence, typed evidence citing executed steps) or
insufficient_information. Tool calls the model writes as text markup are recovered and counted. Stop
conditions: diagnosis submitted, insufficient information, or 30 turns.

## Engineer mode

A human clicks terminals or wires to place the meter probes, presses panel buttons, switches the breaker, waits,
requests resets, and submits a diagnosis from a form. Every action goes through the same ToolBox and policy.
The trace (same format as the agent's) is saved to `scenarios/engineer_traces/` as the engineer reference
column; the compare view then runs the baseline and the agent on the same fault. No engineer traces are
committed yet.

## Model calls

All calls go to the Meta Model API (`https://api.meta.ai/v1`, Chat Completions, OpenAI SDK). Prices used for
the ledger: $1.25 per M input tokens, $0.15 per M cached input, $4.25 per M output (reasoning tokens count as
output). Muse Wonder is not used.

| Call | Where | Model | Reasoning effort | Typical cost |
|---|---|---|---|---|
| Agent turn (tool calling, whole diagnosis) | `agent/loop.py` | muse-spark-1.3 | low | $0.068 per case (clean holdout mean, 8.3 measurements) |
| Schematic read (transcription with uncertain regions) | `hybrid/pipeline.py`, `scripts/transcribe_schematic.py` | muse-spark-1.3 | medium | $0.06 to $0.08 per read; 3 reads for a consensus, about $0.20 (once per server process in the UI) |
| Netlist repair after a conflict | `hybrid/repair.py` | muse-spark-1.3 | medium | about $0.07 per call; 0 calls per case in the photo-read runs (variants explained every conflict) |
| Technician explanation | `hybrid/explain.py` | muse-spark-1.3 | low | about $0.006 per case |

Spend guard (`eval/spend.py`): $130 total; batches stop at $110, the last $20 is for live UI runs, capped per day
(default $5).

## Safety policy

Enforced in `policy/engine.py` before every tool call, never only in the prompt. It looks only at what a
technician at the panel can see (switch position, protection operations in the session, its own history),
never at the injected fault. Blocked attempts are returned to the caller as errors and counted.

| Action | Verdict |
|---|---|
| read_indicators, wait, get_schematic, update_hypotheses | allow |
| measure_voltage | allow with power on, else block |
| measure_resistance | allow with power off, else block |
| press_button Start | allow up to 3 consecutive start presses (reset by Stop or a power cycle) |
| press_button Stop | allow |
| set_power on after a protection trip | needs human approval, with a reason |
| set_power otherwise | allow |
| perform_action reset_protection | needs human approval, with a reason |
| perform_action bypass_interlock, modify_circuit, replace_part, add_jumper | block, always |
| submit_diagnosis | allow with a confidence and typed evidence citing executed observation steps |

Batch runs deny every approval request; `--approve` simulates a human who approves. The information-gain planner
never asks for approval (it does not re-apply power).

## Scoring and evaluation sets

- **Correct = pole level**: component, failure mode and part (pole or contact) all match the injected fault. For
  latent faults (no visible symptom), insufficient_information is correct. The component-level score is kept as
  a secondary column; "pole left open" (right component and mode, no part) is neither correct nor wrong;
  "confidently wrong" names a wrong component, mode or part. "Justified": the truth has an observational twin
  (identical readings in every state the tools can reach) and the answer was insufficient_information or that
  twin with its part. One function computes all of this: `eval/scoring.grade()`.
- **Evaluation sets**:
  - `s01` to `s08` (hand-written scenarios) and `scenarios/holdout_dev.yaml` (40 faults): dev from the start.
  - `scenarios/holdout_clean.yaml` (43 faults never used before, 38 visible + 5 latent): the clean holdout of the
    pure agent and the baselines (frozen prompt, Oct 27). For the hybrid it became **dev on Oct 28**: the hybrid
    was changed after its clean results were seen; those runs are labelled DEV and their folders end in `_dev`.
  - **Final unseen test: a second circuit**, not yet built. Nothing in the frozen components may be tuned on it.

## Invariants (must never break)

1. **No fault leak.** The agent, the planner and every model call never receive the injected fault or the true
   netlist through any channel (prompt, tool output, logs, UI events before "done"). Tests:
   `tests/test_no_leak.py`, `tests/test_hybrid.py`, `tests/test_server.py`.
2. **Policy in code.** Every action passes `Policy.check`; the prompt only describes the policy.
3. **Pole-level scoring is the definition of "correct"** in every table, the README and the UI.
4. **Dev versus final.** Results on dev sets are labelled dev; the second circuit is the final test.
5. **Frozen fingerprints.** `scripts/run_scenarios.py frozen_hashes()` records them in every results.json and
   prints them with every hybrid run. Changing a fingerprinted component needs the user's agreement first.

   | Key | Covers | Value |
   |---|---|---|
   | prompt | agent prompt module and tool specs | a194ad85aaa1 |
   | baseline | half-split baseline | 1e6a729e4428 |
   | image_only_prompt_edits | prompt edits for the image-only ablation | a91bbaca5ac4 |
   | hybrid_planner | information-gain planner incl. joint hypotheses | 8e810ad86523 |
   | hybrid_consensus | self-consistency flags | d6cc6febc3c5 |
   | hybrid_wiring_check | wiring variants and final pole check | eaf03d405b12 |
   | hybrid_acceptance | correction acceptance rule | f4826d851d53 |
   | hybrid_repair | repair prompt and region rule | 4fc879e5fadd |
   | hybrid_transcription_prompt | transcription prompt with uncertain regions | 87622a033cc0 |
   | hybrid_explanation_prompt | explanation prompt | 9c88602b5b56 |
   | hybrid_pipeline | pipeline orchestration | 9cafaaeb45d1 |

6. **No prerecorded outputs** in the demo path: every diagnosis in the UI is computed live (saved transcriptions
   are real earlier Muse Spark reads, labelled as saved).
7. **No em dash** in any text.
