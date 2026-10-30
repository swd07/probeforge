# Decision log

Every design decision, newest last: what was decided, why, the alternatives considered, and the evidence. Append new
decisions at the end (see CLAUDE.md). Architecture: [ARCHITECTURE.md](ARCHITECTURE.md). Result reports:
[docs/results/](docs/results/).

## 2026-10-27

### D1. Own simulator instead of ngspice
- **What:** a pure-Python simulator (`src/probeforge/sim/`): relay logic iterated to a stable state, on-delay timer
  and thermal relay in 0.1 s ticks, mechanical interlocks, protection devices that clear shorts, nodal analysis for
  voltmeter, ohmmeter and motor currents. One YAML file drives the simulator, the agent's text netlist and the
  drawing.
- **Why:** the faults live in control logic (contacts, coils, timers, interlocks, trips), which SPICE does not model
  natively; evaluation needs thousands of deterministic runs; the drawing must never disagree with the netlist.
- **Alternatives:** ngspice with relay logic around it (slow per run, an external dependency, event logic still to
  write); a pure logic simulator without nodal analysis (no realistic meter readings).
- **Evidence:** a circuit builds, takes a fault and powers up in under 0.1 ms; tests cover healthy sequences,
  interlocks, measurement physics, every scenario's symptom and every one of the 91 faults.

### D2. Meta Model API through Chat Completions and the OpenAI SDK
- **What:** `muse-spark-1.3` via `https://api.meta.ai/v1/chat/completions`, key from `.env`.
- **Why:** Day 1 checks passed on this endpoint: tool calling (parallel, streamed arguments), strict JSON schema,
  image input. Constraints found and recorded in CLAUDE.md (only `tool_choice: auto`, tool results must follow
  their call immediately, `max_completion_tokens`, no `reasoning_effort: none`).
- **Alternatives:** Responses API, Messages-style endpoint (both exist; not needed).

### D3. Reasoning effort low for the agent loop
- **What:** the pure agent runs at `reasoning_effort: low`.
- **Why:** same accuracy at lower cost and time.
- **Alternatives:** medium.
- **Evidence (dev, s01 to s08):** low 8/8 correct, $0.43, 299 s; medium 8/8, $0.67, 538 s
  (docs/results/dev/2026-10-27_low.md, _medium.md).

### D4. Agent loop robustness instead of prompt tuning on cases
- **What:** recover tool calls Muse Spark writes as text markup, tell the agent its turn budget and warn 5 and 2 turns
  before the cap, neutral task framing that allows "no visible fault"; typed evidence checked by the policy.
- **Why:** dev failures were loop failures (30-turn loops, missing submissions), not reasoning gaps on specific faults.
- **Alternatives:** case-specific prompt hints (rejected: tuning to the test set). The s06 reasoning gap ("230 V
  across a coil means the coil is intact") was left unpatched on purpose.
- **Evidence (dev holdout):** latent faults 1/10 (v1) to 10/10 (v2); visible 25/30
  (docs/results/dev/2026-10-27_comparison.md).

### D5. h30 physics correction (motor model from winding currents)
- **What:** the motor state is derived from the winding currents (nodal analysis, positive and negative sequence),
  line currents are reported in amps. A welded delta-contactor pole while the star contactor is closed is no longer
  "stopped, zero current" but an unbalanced star start (10 A on the tied line, 5.8 A on the others); true bolted
  shorts happen only when contacts tie two supply phases, and FU2 blows there.
- **Why:** dev case h30 (KM4 pole 5-6 welded) was the agent's only confidently wrong answer, and the simulator's
  simplification was part of the cause: it showed a physically impossible symptom.
- **Alternatives:** keep the simplification and exclude such faults (rejected: it would hide a realistic fault class).
- **Evidence:** `tests/test_power_faults.py` covers every welded and stuck-closed power contact. Made before the
  clean run; all earlier results were moved to docs/results/dev/ because they predate it.

### D6. Frozen prompt and a clean holdout of every never-used fault
- **What:** the agent prompt and the half-split baseline were frozen (fingerprints in every results.json), and the
  43 faults never used in development became the clean holdout (`scenarios/holdout_clean.yaml`, 38 visible + 5 latent).
- **Why:** an honest generalization number for the agent.
- **Evidence:** agent 30/38 visible (33/38 with observational twins), 5/5 latent, 4 confidently wrong; half-split
  25/38, 9 confidently wrong (docs/results/2026-10-27_clean.md). The baseline's rules had been debugged against the
  full fault list, which the report states.

### D7. Engineer mode on the same tools and policy, and a spend guard
- **What:** a human can diagnose in the UI with the same ToolBox and policy; traces in the agent trace format. A spend
  ledger refuses batches over the limit.
- **Why:** a real engineer reference column, measured the same way; cost control on a fixed credit.

## 2026-10-28

### D8. Information-gain search is a ceiling, not a peer
- **What:** the information-gain planner on the true netlist is reported as a ceiling for measurement choice with
  perfect knowledge, not as a competitor of the agent.
- **Why:** it needs a complete, exact fault model of this very circuit, which the agent does not have.
- **Evidence:** 35/38 (38/38 with twins), 2.6 measurements per case (docs/results/2026-10-28_review.md).

### D9. The image is as good a circuit description as the netlist
- **What:** the agent may work from the schematic image alone.
- **Evidence:** clean holdout, component level: netlist only 30/38, image only 31/38, both 30/38 (noise)
  (docs/results/2026-10-28_input_ablation.md).

### D10. Hybrid pipeline: Muse Spark reads and explains, a planner measures
- **What:** read (transcription) -> model (fault catalog from the read) -> plan (information-gain on the read,
  readings from the real panel) -> verify (conflicts trigger a netlist correction) -> explain.
- **Why:** the transcription test showed Muse Spark reads the drawing almost perfectly (all 17 components, the whole
  control circuit; errors only at power-circuit wire crossovers), while the agent spends 8.3 measurements per case and
  is confidently wrong 4 times; a planner with a near-right model measures far less.
- **Alternatives:** keep improving the agent prompt (frozen; tuning risk); give the planner the true netlist (not
  available on a real panel).
- **Evidence:** docs/results/2026-10-28_hybrid.md.

### D11. Unprinted values are unknowns, not defaults
- **What:** a missing timer delay or trip time becomes a candidate grid (1, 3, 10, 30 s; 3, 10, 30 s); without a
  motor rating, currents are compared as zero / nominal / overcurrent only.
- **Why:** with the simulator's default 0 s delay the planner confidently diagnosed a KM4 fault as "KT stuck".
- **Evidence:** offline dry run, docs/results/2026-10-28_hybrid.md.

### D12. Reasoning effort medium for transcription and repair
- **What:** schematic reads and netlist repairs run at medium effort; explanations at low; the agent loop at low (D3).
- **Why:** these calls are few and cheap (a read $0.06 to $0.08, a repair about $0.07), every reported hybrid run used
  medium, and lowering it would change the pipeline behind the dev numbers. The budget rule "no medium effort" applies
  to the agent loop only (user correction, Oct 28).

### D13. Pole-level scoring
- **What:** correct = component, failure mode and part. Component level stays as a secondary column; "pole left open"
  is neither correct nor wrong; justified twins must be named with their part. Every saved run was rescored.
- **Why:** the phone-photo round showed two KM3 star-pole faults named with the wrong pole at confidence 1.0 and
  counted as correct; a technician would replace the wrong pole.
- **Evidence:** the earlier hybrid result went from 29/38 (0 confidently wrong) to 25/38 (2 confidently wrong) at pole
  level; the agent stays at 30/38 (docs/results/2026-10-28_pole_level.md).

### D14. The clean holdout became dev for the hybrid
- **What:** from the evening of Oct 28 every hybrid result on the clean holdout is labelled DEV (folders end in
  `_dev`).
- **Why:** the hybrid was changed after its clean results were seen. The final unseen test will be a second circuit.
  The agent's and the baselines' clean numbers stay clean (frozen before the run).

### D15. Draw the mechanical interlocks
- **What:** the renderer draws the IEC mechanical interlock symbol (dashed linkage with an inverted triangle).
- **Why:** it drew none, so no transcription could find the interlocks.
- **Evidence:** before, 2 of 12 transcriptions listed them (probably from domain knowledge); after, 3 of 3.

### D16. Correction acceptance rule
- **What:** a repair proposal is rejected if it changes fault-free behaviour that no reading contradicted (recorded
  steps the model reproduced must stay reproduced; a generic fault-free run may change only in kinds of fields some
  reading contradicted).
- **Why:** a bad correction (a motor terminal tied to the wrong net) was accepted because it explained the readings,
  and led to a confidently wrong answer.
- **Evidence:** all 10 rejected proposals in the round-1 runs would have broken the fault-free machine (checked
  against the truth afterwards) (docs/results/2026-10-28_dev_changes.md).

### D17. Budget rules
- **What:** smoke test on 5 cases before any full batch; cost estimate before any batch over $2; one full run per
  configuration; no Muse Wonder; spend limit $130 with $20 reserved for the public demo (daily cap for live runs).
- **Why:** about $106 of credit left, a card attached after that.

### D18. Joint hypotheses over fault x wiring
- **What:** alternative wirings of the flagged regions become part of each candidate; they are tried first on a
  conflict and added around the leading component before any power-off decision; the planner counts distinct faults,
  measures across a part's own terminals (also stop, then start held) and reports a pole only when one remains.
- **Why:** the round-1 wiring check could only drop poles after the fact (pole-level correct fell to 20/38); measuring
  to separate the wirings recovers the pole.
- **Alternatives:** keep dropping poles (honest but weak); ask Muse Spark to fix the wiring (it never restored the
  exact netlist in 35 corrections).
- **Evidence:** phone-photo reads, pole level: 27/38 before the changes, 20/38 after round 1, 32/38 (best read, 0
  confidently wrong) and 28/38 (worst read) with joint hypotheses; Muse Spark's repair was never called because
  wiring variants explained every conflict (docs/results/2026-10-28_joint.md). An earlier variant that added the
  variants only after the planner had switched the power off reached only 25/38 and 23/38.

### D19. Corrections only inside flagged regions, at most two rejections
- **What:** Muse Spark may rewire only terminals in flagged regions, or must name a new region with a reason; after two
  rejected proposals in a case no more are requested.
- **Why:** the flags mark where the read itself is unsure; rewiring elsewhere overrides parts of the read that nothing
  questioned, so it must at least be declared and justified. Asking again after a rejection had diminishing returns: in
  round 1 the next proposals for the welded KM2 poles (c15, c18) passed the acceptance rule but explained the readings
  with the wrong fault.

### D20. Self-consistency flags
- **What:** the schematic is read 3 times; terminals whose connections differ between the reads are uncertain too; the
  read that agrees most with the others is the model. The UI's live read uses this.
- **Why:** joint hypotheses can only be as good as the flags; the worst photo read's own flags missed part of the
  misread wiring.
- **Evidence:** on the three saved photo reads: the disagreement regions cover every terminal of every wrongly read net;
  read 1 goes from 28/38 (4 confidently wrong) to 32/38 (0) with them; without any flags both reads give 26/38
  (docs/results/2026-10-28_consensus.md).

### D21. Hybrid frozen
- **What:** the planner (joint mode), consensus, wiring check, acceptance rule, repair and transcription prompts,
  explanation prompt and pipeline are fingerprinted in `frozen_hashes()` and printed with every hybrid run; no changes
  without telling the user first.
- **Why:** the second circuit will be the final unseen test, so the method must be fixed before it exists.

## 2026-10-30

### D22. ASCO Series 300 Group G transfer switch as the Level 2 bench and final unseen test
- **What:** a second bench models a real automatic transfer switch (ASCO Series 300 Group G, 200 A, 208 V, service
  entrance) from the manufacturer's wiring diagram 978741 and the Group G Controller User's Guide 381333-400 N. Its
  held-out faults are the final unseen test (ARCHITECTURE.md). The star-delta circuit stays Level 1 with all its results.
- **Why:** real equipment of critical infrastructure (data centers, hospitals) instead of a textbook circuit; the
  documents fix the components, terminals, wire list and controller sequence, so the model cannot drift into an
  invented circuit.
- **Alternatives:** a second invented relay circuit (rejected: not real equipment); only the star-delta circuit
  (rejected: no unseen test left).
- **Evidence:** the plan of Oct 30 lists what each drawing sheet and guide page documents (docs/ATS_MODEL.md).

### D23. Plan decisions for the ATS bench (approved Oct 30)
- **Agent:** P0 is the pure agent on the ATS (own prompt and tool specs, frozen before the holdout). Hybrid v2 (the
  frozen hybrid plus ATS extensions) is P1 for Nov 2, only if P0 is done by Nov 1 evening, and is frozen before the
  holdout is built; Hybrid v1 stays the method behind the star-delta numbers.
- **Scenarios:** main pair with the same first symptom (generator running, load not transferred, UPS draining):
  A, operator circuit failure (ER commanded, TS does not operate); B, generator running but not accepted (emergency
  sensing circuit open, so no transfer command). Position feedback failure stays an extra dev case: it does not drain
  the UPS and Position Error behaviour is undocumented.
- **No fuse scenario:** 978741 shows no fuse in the TS operator circuit. Replaced by the cut-off contact to coil
  burnout chain, labelled as an assumption for the engineer.
- **Undocumented controller behaviour** (when Transfer Failure and Position Error are declared, what follows):
  labelled assumptions until the engineer reviews them.
- **Simulation parameters:** UPS autonomy 10 min, 30 s of virtual time per reading or action, both labelled.
- **Action tiers (policy in code):** approval for replacing the coil, repairing a wire or connector, replacing or
  adjusting a cut-off contact, replacing the controller; strong approval for a repeat transfer attempt after a failure
  or a second replacement after a repeat failure; never for manual handle operation under load, bypassing interlocks,
  paralleling sources.
- **52U** is the Normal disconnect; the outage is on the utility side and 52U stays closed.
- **Budget:** up to about $4 for the ATS smoke test, holdout run and Hybrid v2 reads. Voice stays P2.

### D24. Our own redrawing of 978741, vendor documents out of git
- **What:** the repository, the UI and the video use our own redrawing (`docs/asco_300g_978741.svg`, generated from
  the netlist) with the source on the drawing: "Redrawn from ASCO Series 300 Group G wiring diagram 978741,
  Schneider Electric. Not the official drawing."; the README links the public Schneider / ASCO library. The vendor
  PDFs stay in `docs/vendor/`, excluded from git. Hybrid v2 reads the original public drawing locally (not committed).
- **Why:** the drawings are copyrighted; the redrawing must never be presented as the official drawing.

### D25. Public demo replay only as a labelled "recorded real run"
- **What:** invariant 6 is relaxed: a public demo may replay a run recorded earlier, only when it is clearly labelled
  "recorded real run"; live runs stay available with the daily cap.
- **Why:** the demo must work for judges even when the API or the budget is limited, without presenting a replay
  as live.

### D26. How the ATS netlist is modelled (stage S0)
- **What:** harness wires and plug/jack pins are parts (each documented wire can fail open, as on sheet 6); the
  controller's SE, ER and NR relays are contacts between jack pins, their coils driven by the controller logic; the
  controller's sensing and position inputs and the TB/TS points are single-terminal parts; a second source
  (`alternate_supply`) is the generator. Loader and renderer changes are additive (new part kinds, optional rails,
  mirrored row items, shared terminals, labelled stubs, a source note on the drawing).
- **Why:** faults on connections are the realistic failures of this circuit; the wire list makes them documentable.
- **Evidence:** `tests/test_ats_netlist.py` (independent transcription of the sheet 6 wire list, documented paths of
  sheets 2, 3, 4, provenance of every part and net, drawing hooks); the star-delta SVG and every Level 1 test unchanged.
