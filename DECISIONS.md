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

