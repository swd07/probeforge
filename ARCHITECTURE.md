# ProbeForge architecture

ProbeForge diagnoses a hidden fault in a simulated ASCO Series 300 Group G automatic transfer switch (our redrawing of
wiring diagram 978741) during a utility outage. Three diagnosticians work through the same tools and the same safety
policy: a Muse Spark agent, Hybrid v2 (Muse Spark in three checked roles around an information-gain planner) and a
human in Engineer mode. The first stage, a star-delta motor starter, is described in
[docs/ARCHITECTURE_LEVEL1.md](docs/ARCHITECTURE_LEVEL1.md); it still runs under "Motor starter" in the UI on a local server; the public demo shows only the ATS bench.

## Code map

| Path | What |
|---|---|
| `src/probeforge/ats/bench.py` | The bench: sources (utility, generator), the Group G controller sequence, the transfer mechanism, coil burnout, the UPS countdown; deterministic |
| `scenarios/circuits/asco_300g_978741.yaml` | Our netlist of the switch, every part and net with its source |
| `src/probeforge/ats/faults.py`, `ambiguity.py` | The fault catalog (118 faults; 49 change the controller face 60 s into the outage, the random-fault pool) and the observational twin check |
| `src/probeforge/ats/tools.py` | The toolbox: panel, meter, isolation, manual operation check, repeat transfer, repairs, diagnosis; 30 s of virtual time per reading or action; arguments checked against each tool's schema |
| `src/probeforge/ats/policy.py` | The safety policy: allowed / approval / strong approval / never, with the evidence rule for strong approvals |
| `src/probeforge/ats/agent.py`, `prompts.py` | The Muse Spark agent loop (Chat Completions, tool calling, low reasoning effort) |
| `src/probeforge/ats/agent_responses.py` | The same loop on the Responses transport: an experiment kept for D38, not used by the UI or the holdout |
| `src/probeforge/ats/hybrid/` | Hybrid v2: `read.py` (transcription), `pipeline.py` (sequence check, repair, acceptance), `explain.py` (explanation and its check) |
| `src/probeforge/ats/infogain.py`, `nextstep.py` | The information-gain planner (also the baseline on the true netlist) and the next-step view for the UI |
| `src/probeforge/ats/freeze.py` | Fingerprints of everything the holdout depends on |
| `src/probeforge/server/` | FastAPI app and WebSocket sessions (`ats.py` for this bench), approvals, the local UI run list |
| `src/probeforge/eval/` | Traces, scoring, the spend ledger |
| `web/` | Vite + React + TypeScript UI |
| `scripts/` | Run, evaluation and maintenance commands; see [scripts/README.md](scripts/README.md) |

## The bench

`AtsBench` simulates the installation after the utility fails: the generator starts, the controller accepts the
Emergency source and commands the transfer, the TS operating coil moves the mechanism, cut-off contacts end the
command, and the load moves to Emergency. A fault (open, stuck, burnt, jammed) changes that sequence; the controller
face shows what a technician would see (lights, display, alarms, event log, metering). The UPS drains while the load
has no source; at 0 the critical load counts as lost. Documented behaviour and assumptions, with sources:
[docs/ATS_MODEL.md](docs/ATS_MODEL.md).

## Tools and policy

Every call goes through `AtsToolBox.call`:

1. The arguments are checked against the tool's advertised JSON schema (D47); anything outside it is an error.
2. `AtsPolicy.check` decides the tier from the call and the panel state (isolated, load powered, failures so far).
3. Approval tier: the approver (a human in the UI, the batch rule in evaluations) is asked with the reason. Strong
   approval: refused in code unless the request has a reason and cites at least one executed instrument reading
   (`evidence_steps`); the policy's own facts (for example "the load is powered from Emergency") are shown to the
   approver next to the requester's reason.
4. The tool runs on the bench; readings take virtual time.
5. `AtsPolicy.record` counts the outcome; instrument evidence comes from what executed, never from arguments (D47).

The tier table is generated from the policy code into docs/ATS_MODEL.md and shown in the UI.

## Diagnosticians

**Agent** (`ats/agent.py`). Input: a system prompt with the task and the policy summary, an image rendered from our
netlist (our redrawing), the netlist as text on request, and the panel as first observation. It calls tools, keeps an
explicit hypothesis list through `update_hypotheses`, and finishes with `submit_diagnosis` (or insufficient
information). Muse Spark 1.3, Chat Completions, low reasoning effort.

**Hybrid v2** (`ats/hybrid/`), three Muse Spark roles, each checked by code:

```
crops of the original drawing --read (x3, medium)--> transcription --consensus--> netlist + flagged regions
netlist --documented fault-free sequence check-- fails --> repair (medium) --> accepted only if the sequence holds
netlist + variants for flagged regions --> information-gain planner --readings--> diagnosis
   a reading no candidate explains --> repair of the region, planner rebuilt, readings replayed
diagnosis --explain (low, strict JSON)--> code check (part by kind, root cause first, isolation sentence, safety
   wording, executed citations) --> one retry --> template
```

The saved transcriptions in `scenarios/transcriptions/ats/` are real earlier reads, labelled as saved in the UI, so
the hybrid runs without the drawing crops (which are not in the repository).

**Info-gain baseline.** The same planner on our true netlist: a ceiling for measurement choice, not a peer.

**Engineer mode.** A human uses the same tools and policy on the same screen; an optional planner suggestion marks the
trace as assisted.

## Model calls

| Call | Input | Output | Effort |
|---|---|---|---|
| Agent turn | messages, image, tools | tool calls | low |
| Read (hybrid) | seven drawing crops, the transcription spec | YAML netlist | medium |
| Repair (hybrid) | the crops, the region, the contradiction | a corrected region | medium |
| Explanation (hybrid) | diagnosis, readings, part names | strict JSON (`response_format` json_schema) | low |

All calls go to `muse-spark-1.3` through the Meta Model API (Chat Completions; the Responses transport is an unused
experiment). The key stays on the server. Every model call reserves its estimate in a local ledger before it is sent
and settles the actual cost afterwards (`eval/spend.py`, under a cross-process lock); the public demo uses a separate
ledger. It is a per-machine guard: the provider-side limit on the key is the real cap.

## Server and UI

FastAPI serves the built UI and one WebSocket per browser tab. A session streams tool events (with the probe points,
the panel snapshot and the planned next reading), approval requests and the final result; the injected fault appears
only in the final result. After a run ends, the server appends the fault to a local, git-ignored list of UI runs
(D44), which the holdout sampler excludes. The UI shows the status column, our redrawing with live probes, the
hypotheses and the step log; Compare runs the other diagnosticians on the same fault.

With `PROBEFORGE_PUBLIC=1` (the hosted demo, [docs/DEPLOY.md](docs/DEPLOY.md)) the server warms up at start and
`/api/ready` answers 503 until then (D62); approval cards wait 120 s (600 s on a private server; the hosted demo sets
300 s, D66) and a connection with no message for 600 s is closed. Live model calls time out after 120 s (360 s with a
live drawing read) and are retried once only when nothing was billed (D58, D59).

## Evaluation

- Dev: 12 hand-written cases in `scenarios/ats/`.
- Holdout: 28 cases sampled by seed after the freeze (`scripts/ats_holdout.py`, D45), run once (D46); the run's code
  is the tag `holdout-2026-10-31`.
- `scripts/verify_results.py` checks the committed records and the published tables offline;
  `scripts/ats_identity.py` proves that a change to frozen code leaves the hybrid's and the baseline's tool logs and
  diagnoses unchanged (D47).

## Invariants (must never break)

1. **No fault leak.** No diagnostician and no model call receives the injected fault or the faulty state through any
   channel (prompt, tool output, logs, UI events before the result). The agent does receive the fault-free schematic
   and netlist, by design; only the baseline uses our netlist for planning. Tests: `tests/test_ats_agent.py` (the
   prompt for all 118 faults), `tests/test_server_ats.py`; the motor starter has `tests/test_no_leak.py`.
2. **Policy in code.** Every action passes `AtsPolicy.check`; the prompt only describes the policy.
3. **Part-level scoring is the definition of "correct"** in every table, the README and the UI.
4. **Dev versus holdout.** Dev results are labelled dev; the holdout is the only unseen test.
5. **Frozen fingerprints.** `ats_frozen_hashes()` (`src/probeforge/ats/freeze.py`), pinned by a test. Changing a
   fingerprinted component needs the user's agreement and a decision entry. They cover the listed components, not
   every dependency (for example `sim/netlist.py` and the drawing crop bytes). Current values (after D47 and D50):

   | Key | Covers | Value |
   |---|---|---|
   | ats_agent | agent loop and prompts | b3e681a84e0d |
   | ats_agent_loop | the shared loop helpers it imports | efe23395808d |
   | ats_tools | toolbox and tool schemas | 8a43235111f3 |
   | ats_policy | safety policy | 832a926080c6 |
   | ats_bench | bench and circuit file | 1897f5e2aa3e |
   | ats_faults | fault catalog and twin check | 2f3ffeba22da |
   | ats_scoring | scoring | 6eb679a9fe4f |
   | ats_transcription_default | the default saved transcription | 7d269af0a274 |
   | ats_hybrid_read | read step and its prompt | 08b4676a5c4b |
   | ats_hybrid_pipeline | sequence check, repair, acceptance | 8a9c95c16c71 |
   | ats_hybrid_explain | explanation step and its check | 9850f995df8b |
   | ats_infogain | planner and baseline | 2eff9c8764c1 |
   | ats_sheet_crops | crop coordinates | 5687e25c8ce3 |

   The holdout ran with the values stored in `scenarios/ats_holdout/holdout.yaml` (tag `holdout-2026-10-31`); D47
   changed ats_tools, ats_policy and ats_hybrid_explain; D50 changed ats_hybrid_explain again. The motor-starter fingerprints are in
   `scripts/run_scenarios.py`.
6. **No prerecorded outputs presented as live.** Every diagnosis in the UI is computed live; saved transcriptions are
   real earlier Muse Spark reads, labelled as saved. A public demo may replay a run recorded earlier only when it is
   clearly labelled "recorded real run" (D25).
7. **No em dash** in any text we write (recorded model output is kept as it was).
