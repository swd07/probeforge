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

### D27. ATS bench simulator (stage S1)
- **What:** `src/probeforge/ats/` simulates the documented Group G 3ATS sequence (SE drops and 1C runs, NR drops for
  the engine start, Emergency accepted at pickup, 2B, ER, transfer; retransfer with 3A, SE, 2E, NR) on the S0 netlist,
  with the transfer mechanism following the sheet 3 cut-off table, the generator started through TB/TS 14-15 and a UPS.
  Undocumented behaviour is in one `ASSUMPTIONS` table (docs/ATS_MODEL.md items 7 to 15). Separate from the relay-panel
  simulator, which is unchanged.
- **Why the manual operation check:** the twin check showed that coil open, jammed mechanism and the burnout chain read
  identically once the coil has burnt (every electrical reading the same), so the root cause could not be found. An
  isolated manual operation check (a jammed mechanism does not move, a cut-off that does not open still reads closed)
  separates them; it becomes an approval-tier action in S2. Labelled as an assumption.
- **Why the metering screen:** three failed emergency sensing inputs were twins with the lights and display alone; the
  documented metering screen shows the measured phase voltages and separates them.
- **Evidence:** tests/test_ats_bench.py (healthy timeline against the guide, every dev symptom, burnout chain and jam,
  no twins in the dev set, no twins across families A and B); full-catalog twin check in docs/ATS_MODEL.md.
- **Approved 2026-10-30** with the three additions as labelled assumptions: the manual operation check is an approval
  tier action, only with both sources isolated and locked out, never under load; the metering screen (guide page 7);
  the controller holds ER / SE after Transfer Failure or Position Error without retry.
- **Wording rule (README, video):** families A and B already differ on the panel (Emergency accepted light, display);
  the agent's real task is localizing the fault within a family with measurements. Never claim that the families look
  identical to the agent.

### D28. ATS tools and four-tier safety policy (stage S2)
- **What:** `src/probeforge/ats/policy.py` (AtsPolicy) and `src/probeforge/ats/tools.py` (AtsToolBox), separate from
  the relay-panel policy and toolbox, which are unchanged. Tiers: allowed / approval / strong approval / never, in one
  `RULES` table that drives the check, the prompt summary and the generated limits table in docs/ATS_MODEL.md. Strong
  approval: a repeat transfer attempt after a Transfer Failure or Position Error (also restoring the sources after one,
  since the controller restarts its sequence), and the same replacement again after a repeat failure. Never: bypassing
  an interlock, paralleling sources, operating the handle under load (including a manual operation check without
  isolation). Resistance, the manual operation check and every repair need both sources isolated and locked out.
  Agent tools: panel, event log, metering screen, wait, voltage, resistance, isolate / restore, manual operation check
  with readings at the other position, repeat transfer attempt with readings during the command (1 s after it),
  repairs. Every reading or action costs 30 s of virtual time.
- **Why:** the engineer's points 4, 5 and 9 (root cause, stronger approval for repeats, a table of action limits);
  the S1 twin check needs the manual operation check and a reading during the command to localize family A.
- **Changed at approval (2026-10-30):** isolating the sources is always approval tier (lockout / tagout is a formal
  procedure on a real site, even with the load unpowered; the batch approver approves that tier, so batch runs can
  still measure resistance). Strong approval is enforced in code: a strong-approval request without a reason and at
  least one cited executed instrument reading (`evidence_steps`) is refused before it reaches the approver; the UI asks
  for a second confirmation in S4. Confirmed: assumptions 16 to 18, no repair for a jammed mechanism (diagnose and
  escalate to vendor service; this ATS has no bypass), the generated limits table with its sync test.
- **Evidence:** tests/test_ats_tools.py: every tier, repeat transfer and second replacement at strong approval,
  resistance and manual operation only isolated, the replaced coil that does not fix a root cause, and the no-leak
  test over all 118 ATS faults (a fault never adds a mention of itself compared with a healthy bench driven the same
  way; no failure-mode word or scenario text in any result).

### D29. ATS agent profile (stage S3)
- **What:** `src/probeforge/ats/prompts.py` and `src/probeforge/ats/agent.py` (run_ats_agent), with the S2 tool specs; the
  relay-panel agent (prompts, tool specs, loop) is untouched and its frozen "prompt" fingerprint is unchanged (a test
  checks it). The prompt describes the equipment from the manufacturer's documentation (sequence, acceptance
  settings, controller face), general meter facts and the labelled bench parameters; it carries no hints derived from
  the dev scenarios (a test checks that no dev fault location appears in the prompt or tool specs; the solenoid A-B is
  the only solenoid). Same loop protocol as the relay-panel agent, effort low, batch approver approves the approval tier
  and denies strong approval. Every case starts 60 s after the Normal source fails. `scripts/run_ats.py` runs cases,
  records spend and writes the table; a7 accepts either misadjusted cut-off as the root cause (`also_accepted`).
- **Why:** P0 is the pure agent on the ATS (plan decision 1); a separate profile keeps Level 1 identical.
- **Evidence:** 5-case dev smoke test 2026-10-30 (runs/20261030_174105_ats_agent_low, dev, not holdout): 4/5 exact,
  the fifth names the right part with the observational twin mode (coil burnt instead of open), 0 confidently wrong,
  $0.52.
- **Motivating finding (X1, position feedback):** the generator was feeding the load, yet the agent asked to isolate
  both sources with the reason "load on UPS". The policy flagged the powered load, but isolation was only approval tier,
  so the batch approver let it through. A demo moment: the agent was wrong, the policy caught it.
- **Changed at approval (2026-10-30), a general policy rule:** isolation that would drop a powered load is strong
  approval (reason plus a cited reading, then the second confirmation; batch denies it). The policy itself adds the fact
  to the request shown to the approver ("Load is currently powered from the Emergency source; isolation will
  de-energize it."), so a wrong agent reason is visibly contradicted. The source is inferred from what the panel shows
  (Normal lost: Emergency). The smoke test was not rerun. Checked: the agent already sees the UPS time left (autonomy,
  time left, draining) in the step 0 observation, every read_panel and every wait; the prompt wording is unchanged.

### D30. ATS bench in the web UI (stage S4)
- **What:** the ATS bench is chosen in the top bar (Motor starter / ATS). `src/probeforge/server/ats.py` runs ATS agent
  and engineer sessions on the same WebSocket (`"bench": "ats"`); the relay-panel sessions are unchanged. The ATS
  panel shows the sources, the transfer switch position (the mechanism flag at the switch), the load, the UPS time
  left (labelled simulation parameter), the controller lights, display, alarms, event log and metering screen, and
  the UPS status flow (Fault detected, Diagnosis in progress, Root cause identified, Awaiting authorized intervention,
  Power restored, Transfer verified). After any diagnosis the session stays open for the authorized intervention
  (isolate, repair, restore) through the same toolbox and policy; "Transfer verified" is set only when the simulator
  confirms the load on Emergency with the position confirmed by the controller, and the countdown stops there.
  Engineer mode: meter on clicked terminals (a click within 14 px snaps to the nearest terminal; A = B refused),
  readings during a repeated transfer command, the manual operation check, cited readings for strong approval. The
  strong-approval card shows the policy's facts and the cited readings and needs a checkbox plus a second confirmation.
  The limits table in the UI comes from the policy code. The TS17 label overlap is fixed by moving the position
  contacts one column right (layout only).
- **Why:** P0 needs a working UI on the ATS; the engineer's points 6, 7 and 9.
- **Note:** the mechanism position is shown to the human on the panel; the agent's tools do not report it (the agent
  infers it from readings). The hybrid pipeline and Compare are not offered on the ATS (P1).
- **Evidence:** tests/test_server_ats.py; browser walkthrough 2026-10-30 (engineer A1 and B1 to Transfer verified, one
  agent run on A7: correct root cause, $0.17).

### D31. Tool parity: the mechanism position indicator (S6 item 1, before the freeze)
- **What:** new agent tool `read_position_indicator` (allowed tier, functional evidence, 30 s like any reading) that
  returns the position flag on the TS mechanism: the information the human sees on the UI panel. Labelled assumption 19
  in docs/ATS_MODEL.md (our two documents do not show the indicator). In Engineer mode the panel's position field now
  shows only the value last checked with the same tool (with its time), so the agent-versus-engineer comparison uses
  equal information at equal time cost; in agent mode and after the diagnosis the observer sees it always. The prompt
  gained one clause naming the tool; the no-leak sweep over all 118 faults includes it.
- **Why:** the agent-versus-engineer comparison must use equal information (S4 note: the human saw the position, the
  agent did not).
- **Note:** the S3 smoke results were taken with the earlier tool list; the ATS profile is not frozen yet (S5).

### D32. Hybrid v2 and the info-gain ceiling baseline on the ATS (S6 items 2 and 3, before the freeze)
- **What:** `src/probeforge/ats/hybrid/` (read, pipeline) and `src/probeforge/ats/infogain.py`; the relay-panel hybrid
  modules stay frozen and are only imported (consensus, wiring alternatives, rewired, Usage). Read: Muse Spark reads
  crops of the drawing sheets of 978741 three times into a compact description (devices, contacts, the wire run list,
  unnumbered joints); code builds our netlist from it (wire part ids, plug / jack pins, net names), and 52U, which is
  not on the drawing sheets, becomes a labelled stand-in NSD. Model: the transcription must reproduce the documented
  fault-free sequence (Group G guide, healthy outage and retransfer). Repair: where the model's own simulation departs
  from the sequence is told to Muse Spark with the terminals of that circuit (from the model only, never the true
  netlist; a test renames the true netlist and blocks loading it, and the prompts stay identical); a correction is
  accepted if it gets further along the sequence without losing what worked and stays in a flagged or named region,
  then the check reruns (at most 4 proposals per transcription, shared by every case); conflicts during a case use
  the strict rule (whole sequence, readings explained). A model that still fails the sequence is not planned on: the
  answer is insufficient information. Plan: information gain over candidate faults simulated on the model from the
  scenario state, live readings first, isolation and resistances only when live readings no longer split, joint with
  wiring variants. The same planner on the true netlist is the ceiling baseline (honest note: it needs a complete,
  exact fault model; the catalog is extended with the documented compound fault of the burnout chain).
- **Privacy rule:** only crops of drawing areas are sent (scripts/render_ats_sheets.py, checked by eye): no cover sheet,
  no outline or order page, no title block, no wire list header, no PDF metadata. Vendor PDF and crops stay local.
- **Disclosure:** the crops and the reading conventions in the read prompt were developed on this same drawing during
  S6 (CP J numbering, the enlarged position contact crop, the shared common terminal and repeated wire number notes).
  Read quality on 978741 is therefore dev quality, not a held-out drawing.
- **Speed:** a case took 330 to 420 s, almost all of it simulating broken models in small time steps. The bench now
  steps 1 s while the controller waits for a generator that is not running up, and looks faults up in a set; recorded
  behaviour of all 118 catalog faults plus the healthy case (twin-check signature and full outage and retransfer
  timeline) is identical before and after (scripts/ats_behaviour_dump.py). With the early exit, the early-stopping
  sequence check, at most 12 wiring alternatives evaluated and the candidates simulated once per transcription, a case
  takes 0.1 s on a failing model and 0.5 to 2.5 s on a passing one (one-time warm-up about 80 s per transcription).
- **Evidence:** tests/test_ats_hybrid.py; dev reads in runs/*_ats_reads (connections up to P 0.97 / R 0.96 without the
  52U region); info-gain baseline 10/12 dev cases correct, the other two honest insufficient information (controller
  internal twins; X1 needs isolation of a powered load, strong approval, denied in batch).

### D33. Hybrid v2 repair: traced circuits, no guessing, contact-type quality (S6)
- **What:** the sequence check names the failing circuit by tracing the transcribed model: from the model's solenoid
  part (found by its kind) through wires, pins, relay contacts and the cut-off contacts of the direction checked,
  stopping at the source phases; the same for the engine start (from the documented TB/TS 14 and 15 field terminals)
  and the sensing and position circuits (from the documented controller ports). The retransfer to Normal is checked
  like the forward transfer (simulated solenoid voltage right after the command). No terminal list is written by
  hand; a test renames the true netlist and blocks loading it, and the check and the prompts stay identical. If the
  check cannot name a circuit, no repair attempt is made. Read quality gains the controller relay contacts (relay,
  terminals in either order, make or break), because the connection metric cannot see a make / break or relay
  attribution error; a repair that makes any metric worse is flagged; every accepted model version is saved.
- **Why:** smoke run 20261031_001944: repair accepted only the two correct fixes and rejected both bad proposals, but
  the retransfer check named no circuit, so the last two attempts were guesses.
- **Disclosure (results):** the hybrid pipeline (crops, reading conventions, sequence checks, repair messages) was
  developed on this one drawing, after seeing the errors of these reads; generalization to other drawings is not shown.

### D34. Hybrid v2 frozen (2026-10-31)
- **What:** after the smoke rerun on the saved reads (runs/20261031_003748_ats_hybrid: the model passes the documented
  sequence after 2 accepted repairs, 5/5 dev cases correct, 0 confidently wrong, $0.19), Hybrid v2 is frozen:
  `src/probeforge/ats/freeze.py` fingerprints the read step with its prompt (08b4676a5c4b), the pipeline
  (7f2625bda2ac), the information-gain planner, also the ceiling baseline (2eff9c8764c1), and the drawing crops
  (5687e25c8ce3); a test pins them and every hybrid run writes them to frozen.json. Line endings are normalized so a
  CRLF checkout gives the same values. The agent profile and the ATS policy and tools are frozen with S5.
- **Why:** freeze before any fresh-read run and before the holdout exists, so the hybrid cannot be tuned on them.
- **Read quality on the saved reads (dev):** transcription relay contacts 4/8, after repair 1 5/8, after repair 2 8/8;
  connections without the 52U region P 0.967 / R 0.957 before, P 1.0 / R 0.967 after; nets exact 72/83 then 74/83
  (the rest: 52U, not on the sheets, and the dashed optional neutral poles). The second repair, asked about the forward
  transfer circuit, also moved the contact J5-J15 that only the retransfer needs: the traced region contains it.

### D35. Sources for the ATS assumptions; mechanism travel under 100 ms (2026-10-31)
- **What:** every bench assumption has a status (documented, supported, assumption) and a source in
  docs/ATS_MODEL.md and in `ASSUMPTION_STATUS` (src/probeforge/ats/bench.py), from public manufacturer sources
  (guide, Schneider FAQs, the Series 300 D-design operator's manual, ASCO patent US7898372B2, the Series 300 brochure).
  One parameter changed: mechanism travel 0.15 s to 0.08 s (brochure: open transition load transfer under 100 ms;
  status supported). The replace_coil result recommends relubricating the operator (operator's manual), text only.
  Known limits added: the coil resistance reading spans the bridge rectifier, the power-up Position Error of the
  retrofit FAQ is not reproduced, under-frequency and an open generator breaker are not modelled, readings are steady
  state.
- **Evidence of no behaviour change from the travel time:** the recorded behaviour of all 118 catalog faults plus the
  healthy case (twin-check signature: panel, display, alarms, metering and event log with causes at five moments, every
  voltage and resistance, the manual check) is identical; in the full outage and retransfer timeline only event times
  move (-0.1 s) and the UPS time left (at most 0.2 s); event names, order, final position and lights are identical. The
  info-gain baseline's diagnoses and reading sequences on the 12 dev cases are identical, the fault-free sequence check
  gives the same events on the 4 saved hybrid model versions, the frozen hybrid fingerprints match.
- **Proposal, not implemented (needs approval):** a healthy switch re-energized after isolation while on Emergency
  raises Position Error in the bench, because the restarted controller starts from Normal. Proposed fix: at power-up
  the controller reads the position contacts and resumes from them (on Emergency with Emergency acceptable: stay on
  Emergency, ER energized; on Normal: the normal sequence), so a restart alone never raises an alarm. Separately, the
  retrofit case of S2 (position inputs read after the source voltage at power-up) could be added as an optional fault;
  it is listed as a limit for now.

### D36. Controller power-up resumes from the position contacts (2026-10-31)
- **What:** approved proposal from D35. On power-up after isolation the controller reads 14A / 14B and resumes from
  the position they give (Emergency: stays there, ER energized, engine start signal; Normal: its automatic sequence);
  with no valid position it shows "Switch Position Unknown" and raises Position Error. A restart alone never raises an
  alarm.
- **Evidence:** the recorded behaviour of all 118 catalog faults plus the healthy case (twin-check signatures and the
  full outage and retransfer timelines) is identical to the previous bench; the info-gain baseline's diagnoses and
  reading sequences on the 12 dev cases, the fault-free sequence check on the 4 saved hybrid model versions and the
  frozen hybrid fingerprints are unchanged. On the isolate-then-restore path (isolated 60 s into the outage, restored,
  60 s later), 78 of 119 cases differ from the previous bench, every one by the same change: the spurious Position
  Error of a switch restarted on Emergency is gone (75 with the load powered, 3 with a main Emergency pole stuck open
  and the load unpowered in both). No case gained an alarm or changed position.

### D37. Responses API transport for the ATS agent, compared before the S5 freeze (2026-10-31)
- **What:** `src/probeforge/ats/agent_responses.py`: the same ATS agent (prompt, first user text, tools, policy, effort
  low, per-turn rules, scoring) over /v1/responses, so the model's reasoning carries across turns. Stateless replay
  only: store false, include reasoning.encrypted_content, no previous_response_id, the instructions on every request,
  our own complete input list replayed (the image only in the first request, then the Chat agent's note), the session
  state local. Cache settings of this transport: a stable prompt_cache_key and prompt_cache_retention "24h". The Chat
  agent's requests are byte-identical; its loop only logs reasoning tokens. `scripts/run_ats.py --transport`.
- **Checked:** Meta docs (Responses protocol, reasoning, prompt caching, tool calling, pricing) and one live check
  ($0.013): encrypted reasoning returned and accepted on replay; reasoning summaries empty for muse-spark-1.3 (not used);
  no cache hit on the second call of that check.
- **Fixed decision rule (before the runs):** one run each of Chat and Responses on the 12 dev cases on the final bench.
  Switch to Responses only if it is not worse on part-level correct and on confidently wrong, and at least 10 % better on
  readings or on cost without the cached-input discount (so the cache hint cannot win alone). A one-case difference in
  correct is not evidence either way. Budget for S6 plus S5 raised to $12.

### D38. Keep Chat Completions for the ATS agent (2026-10-31)
- **What:** by the rule fixed in D37, the ATS agent stays on Chat Completions; the Responses transport stays in the
  repo, unused by the UI and the holdout.
- **Evidence (12 dev cases, one run each, final bench; runs/20261031_012952_ats_agent_chat_low and
  runs/20261031_013347_ats_agent_responses_low):** part-level correct Chat 10/12, Responses 8/12; confidently wrong 0
  and 1 (Responses named the burnt coil, the consequence, in the burnout chain; it did so in the smoke run too); readings
  159 and 108 (32 % fewer); cost without the cached-input discount $1.980 and $1.723 (13 % lower); actual cost $1.135
  and $0.604; cache hit rate 72.8 % and 90.3 %; reasoning tokens 128,004 and 51,777; mean wall time 78 s and 38 s;
  protocol errors 0 and 0. Responses is better on readings and uncached cost but worse on correct and on confidently
  wrong, so the rule keeps Chat. One of the two correct-count differences (the coil read as burnt instead of open) is
  an observational twin, scored justified; one run per transport is a small sample.
- **Pattern (an observation, not proof; one run each):** in both Responses runs (the 5-case smoke and the 12-case run)
  A7 stopped at the burnt coil, the consequence, while Chat found the misadjusted cut-off, the root cause. Responses was
  faster and cheaper but closed earlier; for this domain we keep the more thorough transport.


### D39. The planner's next step in the UI, read from the frozen planner's update hook (2026-10-31)
- **What:** `probeforge/ats/nextstep.py` (not frozen) computes the planner's next step for the UI from the update hook
  of the frozen `AtsInfoGain`, using the planner's own choice (`_best`) and prediction (`_predict`); it changes nothing.
  The run loop calls the hook right before it chooses, with nothing in between, so the plan shown is the step taken.
  Saved transcriptions (the model step of two recorded Hybrid v2 runs) move to scenarios/transcriptions/ats/ so the UI
  and offline checks run the frozen hybrid without API calls.
- **Why:** engineer point 7 (show the next measurement and what it separates) without editing a fingerprinted module.
- **Alternatives:** a hook inside the frozen planner (would change its fingerprint and need a re-freeze); recomputing the
  plan with a copy of the planner logic (could drift from what the run actually does).
- **Evidence (gate, scripts/ats_nextstep_identity.py, no API calls):** 3 models (the baseline on the true netlist and
  the two saved transcriptions) x 12 dev cases: tool logs and diagnoses identical with and without the helper, and all
  186 plans were the step the run then took. Frozen fingerprints unchanged.
- **Privacy of the saved transcriptions:** model outputs only; the export refuses to write if any word of the submittal
  cover page text (the only page with a text layer), not already public in this repo, occurs in the file (0 found for
  both); the free-text words were also reviewed by hand (generic technical words only).

### D40. ATS UI before S5: hybrid session, Compare, troubleshooting sheet, engineer suggestion (2026-10-31)
- **What:** (1) the ATS hybrid session runs the frozen `run_ats_hybrid` on a saved transcription (default: run
  20261031_003748, two accepted repairs) with human approvals; candidates are simulated in the background when the ATS
  bench is chosen (about 80 s); a live re-read is offered only where the drawing crops exist locally, with cost and time
  shown first. (2) The planner's next step is shown before it is taken, with a 1 s display pause per plan (UI pace
  only: no reading, decision or virtual time changes). (3) Compare after any ATS diagnosis: the session's own column
  keeps its live approvals; re-runs (agent, Hybrid v2 on the default saved transcription without the explanation call,
  info-gain baseline) use the batch approval rules; the agent re-run passes the demo spend guard. Engineer column: the
  human's session, else a recorded engineer trace for exactly this fault, else "no engineer trace recorded". (4) The
  troubleshooting sheet (families A and B, one sheet per distinct symptom, so B splits into B1 to B3 by the open
  sensing phase) is generated from the simulator by joint information gain in a safe order, labelled "not reviewed by
  an engineer". (5) Engineer mode can ask for a suggestion: the planner on our redrawing replays the engineer's own
  executed steps (it reads the step log and the isolated flag, never the bench's fault); suggestions are shown only on
  request and the saved trace is marked assisted (Compare shows it). (6) `PROBEFORGE_OFFLINE` makes the server refuse
  model calls (walkthroughs without spend).
- **Why:** engineer points 7 and 8, the S6 Compare and zoom items, the user's ordering and conditions (2026-10-31).
- **Alternatives:** recompute plans in the frozen planner (fingerprint change); show the plan without a pause (it is on
  screen for milliseconds, because replaying a reading on every candidate happens before the plan); an adaptive decision
  tree as the sheet (harder to print and check by hand than a fixed checklist with an expected-reading table).
- **Evidence:** tests (hybrid session over the WebSocket with plans checked against the steps taken, Compare columns,
  the suggestion equal to the baseline plan after the same steps and unchanged with a swapped bench fault, the sheet
  regenerated equal to the committed one and safe-ordered); browser walkthroughs with screenshots in runs/ui_check/.

### D41. New explanation step for Hybrid v2 on the ATS: structured input, checked output (2026-10-31)
- **What:** the explanation moves to `probeforge/ats/hybrid/explain.py`; the frozen pipeline calls it (new
  fingerprints: ats_hybrid_pipeline 8a9c95c16c71, ats_hybrid_explain 1a468df099ba; read, planner and crops unchanged).
  Input, all from the transcribed model and the planner: the diagnosed part by name and kind (for example "operating
  coil TS A-B", "harness wire W7") with its terminals and circuit; every step with its probe points and observed reading;
  for steps that probe the diagnosed part (or a part the same root cause damaged) what a fault-free switch would read at
  that moment, every other step marked "normal for the present position (explained by the diagnosed fault)"; actions
  (isolation, the manual check) as actions; twins and consequential faults named. Output: strict JSON (what failed,
  evidence, the part to act on as a model part id, the action), rendered in code. Check in code: the part to act on
  must be the diagnosed part or a twin (consequential parts allowed), and the action sentences must name it by its kind
  and name no other part; one retry with the reason, then a template from the diagnosis. Insufficient information
  always gets the template (every part still possible listed), because a model text on no single part risks
  presenting a guess as a finding. Effort stays low.
- **Why:** the live check (a1, coil open, correct) told the technician to inspect TS 6-7. Investigation of the recorded
  explanations: the model got bare readings with no reference (TS 6-7 open is normal on Normal), no idea what the part
  is (the coil called "main contacts", engine-start wire called "sense wiring"), isolation and the manual check as raw
  tuples, and twins hidden behind "confidence 0.5".
- **Alternatives:** prompt wording only (no guarantee); the fault-free value for every reading (tried in the first
  version: a fault-free switch has transferred to Emergency, so for position-dependent readings it misled the model
  again, a1 "TS 6-7 open while a good switch reads near zero"); an action part limited to the diagnosed part in the
  schema (a wrong choice would be forced right and become unmeasurable).
- **Evidence (12 dev cases, default saved transcription, explanation scored by `check_text`):** before (frozen code)
  strict 6 of 12 mismatches, lenient 1 of 12 (a1: the action names TS 6-7); the strict failures are actions that refer
  back to the part ("repair the wire") without naming it. After, three iterations on the same 12 dev cases:
  first version 0 of 12 by the check but 4 templates and a1 evidence still misleading; second 0 of 12, 0 templates;
  final 0 of 12 strict and lenient, 10 model texts accepted on the first try, 2 templates (the insufficient
  information cases). Tool logs and diagnoses identical before and after in every paid run (12 of 12) and offline on
  both saved transcriptions (24 of 24). Cost of the measurements $0.456. The check was built and its aliases fixed
  (pins, wire end labels, "steps 1 and 2") before the after runs; the iterations used the dev cases, so the holdout is
  the first unseen test of the explanation.
- **Known gap:** the check covers the action, not every sentence; a7 repairs the cut-off contact without saying to also
  check the coil it burnt, although the input states it.

### D42. Explanation rule for consequential faults: the root cause first, then the damaged part (2026-10-31)

- **What:** when the remaining candidates hold the diagnosed root with further faults (the documented burnout chain:
  both cut-off contacts of one side stuck closed and the coil they burnt), the explanation's action must name all of
  them by kind: the root part and its co-root (the same misadjustment, the same failure mode) first, then the damaged
  part (test, replace if burnt), with the reason: a replacement coil alone burns again at the next transfer while the
  root cause remains. Added to `check_text` (every consequential part named by kind, no damaged part before the root),
  to the prompt (a chain-specific action rule) and to the template. The check also counts "correct the ..." as an
  action. Hybrid v2 fingerprint ats_hybrid_explain 65fb997fbc54 (was 1a468df099ba); read, pipeline, planner and crops
  unchanged.
- **Why:** the known gap of D41: on a7 the explanation repaired the cut-off contact and never mentioned the burnt coil,
  so a technician following it would restore power to a switch that still cannot transfer.
- **Alternatives:** the coil only as an optional mention (D41, the gap itself); a separate "also check" line appended in
  code after the model text (would not tie the order and reason to the action).
- **Evidence (12 dev cases, default saved transcription, the same scoring with the new rule):** before (the D41 texts
  of runs/20261031_111839, rescored offline with the planners rebuilt, tool logs asserted equal) 1 of 12 strict and
  lenient (a7); after 0 of 12 strict and lenient (runs/20261031_114432). Two iterations on the dev cases: the first
  after run also scored 0 of 12, but a good a7 text was rejected once by the checker ("correct the misadjustment" was
  not an action verb) and the stated reason was muddled ("a repaired contact alone"); both fixed. In the final run a7
  still needed its one retry (accepted on the second try), the other 9 diagnosed cases passed on the first try, the 2
  insufficient-information cases use the template. Tool logs and diagnoses identical to D41 (12 of 12). Cost $0.228.

### D43. Critical load lost when the UPS runs out; floating log; source S7 for the UPS autonomy (2026-10-31)

- **What:** (1) the bench records the virtual time the UPS reaches 0 while the load has no source (exact within the
  tick) and marks the critical load as lost from then on (it stays lost in the record even after a source powers the
  load again). The panel shows "Critical load: LOST (UPS depleted at m:ss after the outage)"; the agent's panel view
  carries `load_lost` and the depletion time. Every ATS trace records the UPS state when the diagnosis was made
  (`ups_at_diagnosis`); the result card shows "UPS time left at diagnosis" and, for a correct diagnosis, "Diagnosis
  correct, but the UPS ran out before the diagnosis / the repair: critical load lost"; Compare and the agent and hybrid
  results tables show the same value, and the tables count diagnoses made before the UPS ran out (the S5 metric).
  (2) The step log moved out of the right column into a panel floating over the drawing, toggled, following the newest
  entry unless the reader scrolled up, kept after the run; the same component for the agent, Hybrid v2 (now also each
  planned reading and the explanation) and Engineer mode; no input box. The right column scrolls when it overflows.
  (3) Assumption 14 (UPS autonomy 10 min) cites Schneider Electric (S7: data center battery runtimes 1 to 2 min
  hyperscale, about 5 cloud and colocation, 10 to 15 financial; the battery bridges the 10 to 20 s until the generator
  and transfer switch take over); status "supported" for the autonomy, the load-lost rule and 30 s per step stay ours.
- **Why:** a live agent run (random fault TS:4-20 stuck_open, diagnosed correctly after 21 readings) ran the UPS to 0
  and the UI still read "on UPS" with a plain "Correct": a correct diagnosis after the load is lost is not a success
  for the data center. The log was not visible in that run (pushed below the fold in the right column).
- **Alternatives:** stopping the run when the UPS reaches 0 (hides how long the diagnosis would have taken); a modal
  log (blocks the drawing); a chat-style panel (invites input the agent must never take mid-run).
- **Evidence:** bench tests (depletion inside a long step recorded to the exact time, the flag sticky, the agent sees it,
  no depletion when the transfer comes in time); server test (UPS at diagnosis in the done event); browser walkthrough
  (runs/ui_check 8 to 13): Engineer run waited to depletion, panel LOST at 10:00, result card message; hybrid run on the
  saved transcription with 11 planned readings and the explanation in the log, UPS left 4:00 at diagnosis. Hybrid v2
  and the baseline do not read the new fields (the planner keys panel observations on `ups.draining`): offline on both
  saved transcriptions the diagnoses are identical and the tool logs identical once the new fields are removed. The
  agent sees new panel fields, so the dev agent numbers were recorded before this change (noted in
  docs/results/ats_results.md). Must land before the S5 freeze.

### D44. Local list of UI runs for the holdout exclusion; taller log panel (2026-10-31)

- **What:** the server appends one line per UI session to the git-ignored `runs/ui_runs.jsonl` (bench, mode, fault,
  source, how it ended, time) after the run ends: diagnosis in, stopped, replaced by a new run, or the browser left.
  It is written once per session, never sent to the agent or the planner, and from now on the holdout script excludes
  every ATS fault in it (S5 exclusion (c)). The log panel is now fixed at 72 % of the window height, vertically
  resizable, with a Hide button in its header.
- **Why:** two UI agent runs used random faults before the list existed: 10:38 (TS:4-20 stuck_open, identified from
  the run) and 11:33 (fault not recorded, not remembered). An exclusion that relies on memory is incomplete.
- **Alternatives:** the fault in the spend ledger (the ledger is for cost, and its lines appear in reports); writing at
  the start of a run (a run that never ends would still be listed, but the user asked for after the run ends, and
  stop, replace and disconnect cover runs that do not finish).
- **Evidence:** server test (an Engineer run writes ["TS:A-B open"], mode manual, ended "diagnosis"; tests write to a
  temporary file); browser check of the log at 1600x950 and 1280x720 (72 % of the window, drag resize, Hide and
  reopen; runs/ui_check/14_*).

### D45. S5 freeze of the ATS bench and the holdout procedure (2026-10-31)

- **What:** `ats_frozen_hashes()` now also covers the agent (its module and prompts, the shared loop it imports, the
  tools, the policy), the bench with its circuit file, the fault catalog and twin check, the scoring, and the default
  saved transcription the hybrid runs on (Hybrid v2 read, pipeline, explain, planner and crops were already covered).
  Values: ats_agent b3e681a84e0d, ats_agent_loop efe23395808d, ats_tools 9700f0488e24, ats_policy 2e45800cdaff,
  ats_bench 1897f5e2aa3e, ats_faults 2f3ffeba22da, ats_scoring 6eb679a9fe4f, ats_transcription_default 7d269af0a274;
  ats_hybrid_read 08b4676a5c4b, ats_hybrid_pipeline 8a9c95c16c71, ats_hybrid_explain 65fb997fbc54, ats_infogain
  2eff9c8764c1, ats_sheet_crops 5687e25c8ce3. Tests pin them. Holdout (`scripts/ats_holdout.py`): made once by seed
  20261031 after this freeze, committed with its sha256 before any run; the run refuses to start unless the file
  matches its hash, both are committed unchanged, and the fingerprints equal those stored in the file. 24 visible
  single faults, the other side of the burnout chain, 3 latent faults (28 cases); agent (Chat, low), Hybrid v2 (default
  saved transcription, repair and explanation as in the UI), info-gain baseline; batch approvals (approval tier
  approved, strong denied); first 5 cases the smoke test for technical failures only; cap $6; one run.
- **Exclusions:** every dev fault, the observational twins of the dev cases (stricter than the plan: SE X1-J2, SE
  J5-X2 and ER X2-J16 behave exactly like a3 on every reading, so they are not unseen), every ATS fault in the UI run
  list (D44) and TS:4-20 stuck_open (10:38). The 11:33 UI run's fault is unknown and disclosed.
- **Latent rule (in the file):** correct only with insufficient information; any confident diagnosis is confidently
  wrong, even one naming a twin (the shared `grade` would excuse a justified twin; the holdout scorer does not).
- **Why:** the plan approved on 2026-10-31 with changes a to d.
- **Alternatives:** a hand-picked holdout (not independent); sampling from the whole catalog including dev twins (would
  count a3's behaviour as unseen).

### D46. S5 holdout run and results (2026-10-31)

- **What:** the single holdout run (runs/20261031_123544_ats_holdout, list sha256 9f570d3c...c39e, fingerprints as in
  D45), written up in docs/results/ats_results.md with dev and holdout side by side. Nothing was changed after the run
  started; the smoke test (h01 to h05) had no technical failure.
- **Evidence:** part-level correct agent 17/28, Hybrid v2 18/28, baseline 18/28 (hybrid equal to the ceiling case by
  case); confidently wrong 3, 0, 0 (agent: h06, h10 position-feedback guesses, h25 the burnt coil instead of the
  root cause); latent 3/3 for all; 8 position-feedback faults insufficient information for all three, because
  isolating a powered load needs strong approval and the batch rule denies it; agent 2 correct diagnoses after the
  UPS ran out (h13, h18); explanation check 28/28 (15 model texts, 13 templates); cost $3.54 of the $6 cap.
- **Why recorded:** the results doc is the reference for the README and the demo; the holdout is the only unseen test.

### D47. Post-holdout fixes to frozen ATS code (2026-11-01)

- **What:** three defects an external review found in frozen code after the holdout run, fixed in place (instead of a
  versioned successor), with the run's code kept as the tag `holdout-2026-10-31` (c54809b; its 13 fingerprints were
  checked equal to those in the holdout list before tagging).
  1. `isolate_sources` had no `evidence_steps` in its schema, while the policy requires them for isolating a powered
     load: a schema-obeying agent could not make that request. In the recorded runs (1,154 agent tool calls) the agent
     sent the field anyway, as a JSON string such as `"[1, 2, 4]"`, 15 times, all refused; where the field was in the
     schema (restore_sources, repeat_transfer_attempt) it always sent a list. The field is added.
  2. `AtsPolicy.record` counted any executed call with a `readings` argument as an instrument reading (a fabricated
     `readings` on `read_panel` could satisfy the strong-approval evidence rule). Evidence now comes from what executed:
     the meter tools, and the manual check or repeat transfer only when their result holds readings.
  3. The explanation check accepted repair wording without isolation first. Code now puts one fixed sentence before
     every action, in model texts and templates ("Before any work: open 52U, lock out and tag the generator, and prove
     both sources dead at the work point with a voltmeter."); the check rejects a repair instruction before it,
     energized-work or bypass wording after it unless negated in the same clause, and evidence citing steps that did
     not run. The template's twin sentence and the prompt now say "the same action" (not "the same repair").
  With them the toolbox rejects arguments outside each tool's advertised schema before the policy or the tool sees
  them. The first offline proof differed (72 of 120): the planner's own `submit_diagnosis` carries a `note` (twins or
  causes still possible) that was not in the schema, so that logged call became an error (the diagnosis itself was
  unchanged); with `note` added to the schema as an optional string the proof is identical. Fingerprints: ats_tools
  8a43235111f3 (was 9700f0488e24), ats_policy 832a926080c6 (was 2e45800cdaff), ats_hybrid_explain e327e1021001 (was
  65fb997fbc54); the other ten unchanged.
- **Why:** the review reproduced each defect; the user checked the three in frozen code and chose fixing in place with
  a tag, a decision entry and an offline proof over a successor version.
- **Alternatives:** a versioned successor (the review's recommendation; keeps the frozen modules byte-identical but
  duplicates them); documenting the defects only (leaves the live demo with them).
- **Evidence:**
  - Offline (scripts/ats_identity.py, results/identity/): Hybrid v2 on both saved transcriptions and the baseline, 12
    dev and 28 holdout cases: tool logs and diagnoses identical before and after (120 of 120, after.json), and identical
    to the holdout run's recorded traces (56 of 56). after_without_note.json is the first, differing record.
  - Explanations (12 dev cases, results/runs/20261101_105210_ats_explain_d47_after, $0.114): 0 of 12 failed the check,
    10 model texts on the first try apart from a7 (one retry, the D42 order rule), 2 templates, the isolation sentence in
    12 of 12, diagnoses identical to the D42 run. Before: no D42 text had the sentence; scanned whole, 3 of 12 had
    energized or under-load wording, all outside the action (two in evidence, one negated "do not ... under load", which
    the first version of the rule wrongly flagged: the negation scope was widened to the clause and a test added).
  - Agent, not re-run on the holdout. Post-fix smoke on the 5 S3 dev cases (results/runs/20261101_105449_ats_agent_chat_low,
    $0.598): no technical errors, 0 protocol errors; the schema-valid isolation request reached the strong approver (x1,
    4 requests with list evidence); one call rejected by the schema (a7: manual check without its required reason; the
    agent repeated it with a reason, the step the policy would also have demanded). Outcomes 2/5 correct, 1 confidently
    wrong (a7 named the coil, the consequence, the pattern of holdout h25), a1 named the observational twin "burnt": a
    check, not a result; the S3 smoke had 4/5 and the dev run 10/12 on the old tools, one run each.
- **Not fixed (frozen, documented):** the planner's cache key ignores resistance values; repeated identical readings are
  not counted as redundant. The freeze covers the listed components, not every dependency.

### D48. Drawing provenance stated per diagnostician; vendor folder in .gitignore (2026-11-01)

- **What:** the docs now say exactly what each diagnostician sees (docs/ATS_MODEL.md, "What each diagnostician
  sees"): the agent an image rendered from our netlist plus the text netlist; Hybrid v2's read and repair steps seven
  crops of the original ASCO drawing 978741 from the author's local copy of the submittal package (drawing areas only,
  sha256 of the PDF and of the current crops recorded); the baseline our true netlist. `docs/vendor/` is in
  `.gitignore` (it was excluded only locally before).
- **Why:** the external review found results/runs/README.md saying the netlists were transcriptions of our redrawing,
  which contradicted D24 and the code; and the ignore rule D24 promised was missing from the repository.
- **Alternatives:** committing the crops (copyrighted vendor material; not ours to publish).

### D49. Opaque ATS scenario ids in the browser until the result (2026-11-01)

- **What:** the UI's scenario list and every event before the result use `dev-01` to `dev-12`; the server maps them
  to the case files. The descriptive case id (for example `a1_coil_open`) appears only in the result, next to the
  injected fault. The server test now asserts that no case id is in any event before the result (its exception for
  `a1_coil_open` is removed).
- **Why:** the external review found the case ids, which name the fault, in the browser before the diagnosis, so an
  Engineer-mode run on a dev scenario was not blinded and invariant 1 was narrower than stated. The model prompts never
  carried them.
- **Alternatives:** labelling dev-scenario runs as unblinded demonstrations (keeps a leak the UI does not need).

### D50. Explanation check: a wider unsafe-wording list over the whole text (2026-11-01)

- **What:** a post-holdout fix to frozen code (ats_hybrid_explain 9850f995df8b, was e327e1021001). The D47 list
  applied only after the isolation sentence; it is replaced by three kinds of wording:
  - unsafe anywhere in the text: bypassing, jumpers, defeating, paralleling the sources, skipping the lockout or
    isolation, working without isolating or locking out;
  - unsafe in the action part after the sentence: energized or live work, under load, power on, "hot" (in the
    evidence these words describe readings);
  - re-energizing (restore the sources or power, close 52U, start the generator) when a repair instruction follows;
    "after the repair, restore the sources and verify" passes.
  Paralleling now needs a source as its object ("paralleled readings" passes). A negation covers only its own
  clause: it stops at punctuation and at "and", "then", "but". README and the results doc now say it is a fixed word
  list that narrows what the model can say, not a safety review of the text.
- **Why:** an independent audit passed the D47 check with "Re-energize the switch, then replace...", "Restore both
  sources, then...", "With power on, replace...", "...without isolating the sources", "Skip the lockout and...", text
  placed before the sentence ("Bypass the interlock. "), and a negation 80 characters away ("no reason to delay and
  bypass..."); and flagged "paralleled readings" falsely.
- **Alternatives:** an allow-list for the action field (a fixed opening phrase only; less natural text, and the model
  ignored such constraints in D41); narrowing the claim only (the gaps would stay in the live demo).
- **Evidence:** all ten audit wordings fail the check, four safe wordings pass (tests). The 12 committed D47
  explanation texts all pass the new check, and none of the 28 holdout texts has the new unsafe wordings (they fail
  only for the D47 sentence they predate), so no paid re-run was needed. Offline identity: tool logs and diagnoses
  identical before and after (120 of 120) and identical to the holdout run's traces (56 of 56); the regenerated
  results/identity/after.json carries the current fingerprints, and scripts/verify_results.py now checks that (the
  audit's D2: the committed record had been made before D47's last edit).

### D51. Server hardening before a public demo (2026-11-01)

- **What:** the fixes an independent audit listed before a public deploy, all outside frozen code:
  - S1: blocking work runs in two bounded pools (tool calls; agent, hybrid and Compare runs, refused when full); a
    connection holds at most two tool calls (an approval waiting plus one queued); connections are capped overall
    (40) and per IP (2 in public mode, 10 locally); a connection idle for 10 minutes is closed; approval waits are 120 s
    in public mode (600 s locally).
  - S2: the WebSocket accepts browsers only from the page's own host or an allow-list, and every start needs a
    session token from `/api/session-token` (an HMAC of its time, 10 minutes); uvicorn caps messages at 64 KiB and
    concurrency at 100. Both apply locally too.
  - S6: the spend ledger reserves before every model call and settles after it under its file lock (a metered client
    around the OpenAI client, so the frozen loops are unchanged); a failed run still records what it spent; public mode
    uses a separate ledger from $0. Public runs stop at $0.75 and calls at 10,000 completion tokens: 2.5x the most
    expensive recorded agent run ($0.30) and 2.1x the largest recorded call (4,725 tokens, from 690 calls in the
    committed runs); repairs and live re-reads (up to 19,815 tokens) are off in public mode, so the cap never cuts them.
  - S3: the agent's effort comes from an allow-list (low or minimal; low only in public mode).
  - S4 and C1: every message is validated before dispatch; a bad one gets an error and the socket stays; the session
    always ends with its connection (and gets its UI run row); the page says when the connection is lost.
  - S5: engineer names are slugged before any path use; in public mode visitors' traces go to `runs/visitor_traces/`
    and never into Compare; growing folders keep their newest 200 files.
  - C2: one Compare per result at a time; a replaced run's Compare is dropped; every event carries the page's run
    number and the page ignores older runs.
  One switch, `PROBEFORGE_PUBLIC=1`, turns on the public-only behaviour.
- **Why:** the audit reproduced against a live server that one anonymous client could stall every visitor for 10
  minutes (an approval pending plus queued calls), that any page could start paid runs, that a malformed message
  orphaned a session, that the browser chose the reasoning effort, and that a visitor's name reached a file path.
- **Alternatives:** an asynchronous approval wait (needs the frozen toolbox changed); a provider-side spend limit alone
  (kept as the real cap, but no protection between the server and the key).
- **Evidence:** a test against a real uvicorn process reproduces the stall and passes after the fix; tests for the
  connection caps, the full run pool, foreign Origins, tokens, concurrent reservations (20 threads, never past the
  cap), the metered client, the public ledger, the effort allow-list, malformed messages, the closed connection, hostile
  engineer names, visitor traces in public mode, the run number and the second Compare; Vitest for the reducer
  (connection lost, older runs dropped), run in CI; browser check of the lost connection.

### D52. The explanation for the technician is tidied for display only (2026-11-02)

- **What:** the result card shows the hybrid's explanation through a display formatter in the page
  (`web/src/explanationText.ts`): the repeated step prefix ("Step 20: Step 20 measured ...") becomes "Step 20:
  Measured ..."; readings the model spelled out become numbers with units ("about two hundred eight volts" to "about
  208 V", "zero ohms" to "0 ohm"; only number words followed by volt or ohm, up to 999); hyphens are restored in the
  compounds the model writes apart ("de energized" to "de-energized", "re energize", "fault free", "cut off contact"
  and "cutoff contact" to "cut-off contact"; the verb "cut off" stays). The run record keeps the text exactly as the model and the frozen `render()` produced it, and the
  explanation check scores that text.
- **Why:** `render()` (frozen explain module) writes "Step N:" before each evidence sentence and the model often starts
  the sentence with "Step N" itself: 20 of the 87 distinct recorded explanation texts repeat the prefix. No check
  rule rejects digits (the planner gives the model "208.0 V"); under the frozen prompt's "Plain English, no dashes as
  punctuation" the model spells readings out in 37 of the 87 texts and drops hyphens. These are display problems, not
  wrong explanations.
- **Alternatives:** strip the prefix in `render()`, or a prompt line asking for digits with units: both change the
  frozen explain module (D50 route: new fingerprint, identity proof, offline rescoring; for the prompt also a paid
  re-measure of about $0.20) for a display problem.
- **Evidence:** Vitest cases from the recorded wordings ("Step N: Step N", "Step N: At step N", "Two hundred eight
  volts", "one hundred twenty volts", "Zero ohms", "de energized", "fault free", "cut off contact", "cutoff contact";
  a different step number, digits, number words without a unit and the verb "cut off" are kept). Over the 87 recorded
  texts the formatter changes 62; it leaves a bare "zero" without a unit as written.

### D53. Ids are shown as words on screen, display only (2026-11-02)

- **What:** the page shows the action and tool ids the policy, the tools and the planner send as words
  (`web/src/labels.ts`): approval card titles in sentence case ("Adjust cut-off contact TS:8-9", "Isolate sources"),
  policy reasons ("adjust cut-off contact needs human approval"), the feed's repair line ("Request adjust cut-off
  contact TS:8-9"), the repair list and the part kinds of the diagnosis form ("8-9 (cut-off contact, closed on
  Normal)"). One spelling on screen: "cut-off". Failure modes read as words wherever a fault or cause is shown
  ("TS 8-9 stuck closed": suggestion and next-step cards, candidate faults, result card, feed, Compare, troubleshooting
  sheet, diagnosis form). The "Agent action limits" table keeps every id, the agent's real
  vocabulary, with its label next to it. Run records, traces, the policy and the frozen modules keep the ids.
- **Why:** the dev-07 Engineer walkthrough for the video showed "adjust_cutoff_contact needs human approval",
  "Request adjust cutoff_contact" and the title "Adjust Cutoff Contact" (CSS capitalize) next to "cut-off" in every
  other text; the reasons come from the frozen policy (`f"{action} needs human approval"`).
- **Alternatives:** change the policy's reason strings (frozen module, and the agent sees them as tool results);
  replace every underscore (would change part ids such as `H1:W12_TS1-W12_P12`): only lowercase ids joined by
  underscores are mapped.
- **Evidence:** Vitest cases with the walkthrough's strings; part ids unchanged; no repair label holds an underscore or
  "cutoff".

### D54. Start asks first while a repair is under way (2026-11-02)

- **What:** on the ATS bench, after the diagnosis, while the sources are isolated or restored with the transfer not
  yet verified, the first click on Start turns the button into "End the repair and start new?" for 5 s; only a second
  click starts a new run (`web/src/intervention.ts`). Before any intervention and after "Transfer verified" Start
  stays one click.
- **Why:** after the diagnosis the top bar shows Start again while the intervention goes on; one click started a new
  session and cancelled the repair (seen in the dev-07 walkthrough for the video, a judge would hit it too).
- **Alternatives:** a native confirm dialog (looks out of place in a demo recording); disabling Start until the
  transfer is verified (a repair that cannot succeed would trap the visitor).
- **Evidence:** Vitest for the condition (isolated, restored and not verified, verified, no intervention, motor
  starter bench); browser check of both clicks.

### D55. The intervention is visible on the drawing and in the feed (2026-11-02)

- **What:** after an approved repair has run, the drawing outlines the part in green with a pill under it
  ("adjusted", "replaced", "repaired"; a controller replacement marks all CP parts), and with "follow probes" on the
  view goes to that part (`web/src/repairs.ts`). The feed shows the recommendation a tool returns, verbatim (the coil
  replacement: "relubricate the operator when the TS coil is replaced", from the operator's manual, docs/ATS_MODEL.md
  S3). Denied or pending requests mark nothing. Display only: tools, policy and records unchanged.
- **Why:** in the dev-07 walkthrough for the video the repair moments had no visual on the drawing, and the
  recommendation the frozen tool already returned was never shown.
- **Alternatives:** clearing the diagnosed outline after the repair (the diagnosis stays a fact of the run); marking on
  the request (a denied repair would look done).
- **Evidence:** Vitest for the repaired parts (executed only, controller, a part repaired twice, labels) and the
  recommendation (executed, denied, absent); browser walkthrough of dev-07: pills "adjusted" on TS 8-9 and "replaced"
  on TS A-B, recommendation line under step #6, still 6:17 at "Transfer verified".

### D56. The never tier is visible in Engineer mode, and its count in the committed runs is stated (2026-11-02)

- **What:** the manual operation check in Engineer mode stays enabled before isolation. Pressed under load, the real
  policy blocks it as a never-tier action: the red message and the feed line show the policy's own reason ("manual
  operation under load is never allowed; only with both sources isolated and locked out", ids mapped by labels.ts),
  the run counts 1 blocked and no virtual time passes. The agent action limits show the never-tier attempts counted
  by `scripts/count_never_attempts.py` (`probeforge.eval.never_attempts`) from the tier logged with every step in the
  committed runs (results/runs): agent 0 in 62 runs, hybrid 0 in 38, baseline 0 in 28. The policy is unchanged.
- **Why:** the button was disabled until isolation, so the never tier could not be seen anywhere in the app.
- **Alternatives:** buttons for the three always-blocked actions (bypass interlock, parallel sources, handle under
  load): skipped, they invite a click nobody would make in the field; staging an agent attempt (would not be a real
  run); a fixed number in the text (would drift from the committed runs).
- **Evidence:** pytest: the blocked call (verdict, tier, the policy's reason, no virtual time, counted), the counter on
  a synthetic folder and a tier on every step of the committed runs; Vitest for the count text and the feed title of a
  blocked check; browser check on dev-07 before isolation.

### D57. The explanation says who wrote it; a failed run says why (2026-11-02)

- **What:** the hybrid's explanation is labelled by its source: "Muse Spark", or "fixed template" with the reason
  (insufficient information, which always gets the template; a failed Muse Spark call, e.g. "the Meta API returned an
  error (HTTP 500)"; answers that failed the explanation check). The server reads the frozen explain module's own
  record (`explanation_source` in server/ats_modes.py). A run that stopped on an error shows "no diagnosis" and the
  reason in words; the "Root cause identified" stage is not passed without a diagnosis.
- **Why:** the judge-style check with a simulated Meta API failure showed the template under the label "For the
  technician (Muse Spark)", and an agent run that failed showed "error" as its diagnosis with no reason. Every
  insufficient-information explanation was also labelled Muse Spark although it is the template.
- **Alternatives:** hide the template when the call fails (the template is a correct, checked text the technician can
  use); change the frozen explain module to mark its text (not needed: its record already says so).
- **Evidence:** pytest for the source (model, insufficient information, failed call, failed check); Vitest for the
  labels and the error wording; browser check against a fake API returning HTTP 500.
