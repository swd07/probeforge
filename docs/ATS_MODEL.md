# ATS bench model: documented versus assumed

The Level 2 bench is an **ASCO Series 300 Group G automatic transfer switch**, 200 A, 208 V 60 Hz, 3 phase 4 wire,
service entrance, 4 switched poles (catalog D03AUSB30200CGXM, accessories 11BE and 44G). The model is built only
from two manufacturer documents, which are not part of this repository:

- ASCO wiring diagram **978741** (Three phase wiring for 300 Series transfer switches, D frame, Group G controls),
  sheets 1 to 6, and outline drawing 1522770-003, from the product submittal.
- **Group G Controller User's Guide 381333-400 N** (3/2026).

Public source of the drawings: the Schneider Electric / ASCO technical documents library for the Series 300 Group G
(links in the README). The diagram in this repository (`docs/asco_300g_978741.svg`) is **our own redrawing**, generated
from `scenarios/circuits/asco_300g_978741.yaml`; it is not the official drawing.

Every part and net in the YAML has a source under `provenance`; every undocumented value is under `assumptions`.
`tests/test_ats_netlist.py` checks the netlist against an independent transcription of the sheet 6 wire run list and
against the documented paths of sheets 2, 3 and 4.

## Documented and modelled (stage S0)

| What | Source |
|---|---|
| Main poles TS(NA/NB/NC/NN), closed on Normal, and TS(EA/EB/EC/EN), closed on Emergency, to load LA/LB/LC/LN; terminal numbers TS-1, 2, 3, 4, 19, 5, 20, 21, 22 | 978741 sheet 3 (main power poles) |
| 52U service entrance breaker on Source 1 (Normal): Square D HL/JL, 175 to 225 A frames, thermal-magnetic, manually operated | outline 1522770-003 |
| TS operator circuit: NA - TS 7-6 - P3/J3 - SE (NO) - J2/P2 - solenoid A-B - P5/J5 - SE (NO) - J15/P15 - TS 70-69 - NC; EA - TS 9-8 - P1/J1 - ER (NO) + SE (NC) - J2 ... J5 - SE (NC) + ER (NO) - J16/P16 - TS 72-71 - EC | 978741 sheet 3 (TS operator circuit) |
| TS control (cut-off) contacts: 6-7 and 69-70 closed on Emergency and before TDC toward Normal; 8-9 and 71-72 closed on Normal and before TDC toward Emergency; the cut-off setting is in the test and adjustment procedure | 978741 sheet 3 (TS control contacts table) |
| TS solenoid assembly: bridge rectifier CR and coil between terminals A and B | 978741 sheet 3 |
| Normal sensing NA, NB, NC to controller J12, J11, J4; Emergency sensing EA, EB, EC to J7, J18, J6 (3 phase with accessory 11BE); load LA, LB, LC, LN to J19, J20, J21, J24; NN, EN to J22, J23 | 978741 sheet 4 |
| TS position sensing: aux 14B (NO, closed on Emergency) 17-16 to J13, aux 14A (NC, closed on Normal) 17-18 to J14, common 17 to J10 | 978741 sheet 4 |
| Engine starting signals: controller NR (NC) J8-J9 to TB/TS 14-15, Feature 7 closes to start; NR (NO) J8-J17 to TB/TS 16, Feature 8 opens to start; TS aux 14B across TB/TS 14-15; contacts rated 5 A, 30 V dc | 978741 sheet 2 |
| Every harness wire with both endpoints (harness 337782-003, AWG 20) | 978741 sheet 6 |
| Sequence: SE drops out and Feature 1C runs, NR drops out (engine start, emergency usually accepted about 10 s later), Feature 2B, ER energizes, the TS coil operates and all contacts reverse; retransfer: Feature 3A, ER off and SE on, Feature 2E cooldown, NR on | Guide pages 29 and 30 (used from S1) |
| Source acceptability, pickup and dropout settings (Normal 85 % / 90 %, Emergency 75 % / 90 %), timers (1C 3 s, 1F 4 s, 2B 0, 2E 5 min, 3A 30 min, fail-accept 3 s with the alarm off by default) | Guide pages 7, 14 to 17 (used from S1) |
| Lights (Normal accepted, Emergency accepted, Load on Normal, Load on Emergency, Alert, Not in automatic), display messages, event types and causes | Guide pages 6, 26 to 28, 43 and 44 (used from S1) |

## Sources for the assumptions

Public sources (short quotes only; no vendor PDF is in this repository):

- **guide**: Group G Controller User's Guide 381333-400 N (3/2026).
- **S1**: Schneider Electric FAQ000238967, Functional Test for the Series 300 ATS.
- **S2**: Schneider Electric FAQ000222180, Position Error right after installing a Group G retrofit controller.
- **S3**: ASCO Series 300 D-design 30 to 230 A operator's manual (Winco edition),
  https://www.manualsdir.com/manuals/716169/winco-asco-300-d-design-30-230-amp.html
- **S4**: ASCO Power Technologies patent US7898372B2, https://patents.google.com/patent/US7898372
- **S5**: ASCO Series 300 brochure, https://www.globalpwr.com/wp-content/uploads/cut-sheets/gps-acso-series-300-brochure.pdf
- **S6**: Schneider Electric FAQ000207844, coil resistance values by frame (the D-frame values are only in an image and
  depend on the coil kit).

Status: **documented** (a manufacturer source for this equipment), **supported** (a manufacturer source that does not
cover this exact frame, or a secondary source), **assumption** (no source). The bench values are in the
`ASSUMPTIONS` table of `src/probeforge/ats/bench.py`, their status and source in `ASSUMPTION_STATUS` next to it.

## Assumptions

In the netlist (S0):

| # | Assumption | Status | Source and note |
|---|---|---|---|
| 1 | TS solenoid A-B resistance 30 ohm | assumption | Placeholder. S6 has the real table by frame; the D-frame value depends on the coil kit and is only in an image. See the limit on what the reading spans. |
| 2 | Utility and generator are ideal 120/208 V three-phase sources | assumption | Simulation model. |
| 3 | The generator starts while TB/TS 14-15 is closed (Feature 7); Feature 8 is not used by the modelled generator | documented | 978741 sheet 2 (Feature 7 closes to start, Feature 8 opens to start); which one the site generator uses is a site choice. |
| 4 | Controller inputs are ideal voltage and continuity sensing points | assumption | The controller's internal circuits are not published. |
| 5 | SE, ER and NR are modelled as contacts; their coils are inside the controller | documented | 978741 sheets 2 and 3 show only the contacts; the guide names the relays. |
| 6 | The optional extension harness 309320-005 (Px/Jx) is not modelled: plug P mates directly with jack J | documented | 978741 sheet 6 lists it as an optional extension harness. |

In the bench simulator (S1):

| # | Assumption | Status | Source and note |
|---|---|---|---|
| 7 | **Transfer Failure** if the position contacts do not confirm the other position 6 s after the command while the switch never left its origin | assumption | The guide lists the event; its criteria and timing are not published. |
| 8 | **Position Error** if the switch left its origin but the other position is never confirmed 6 s after the command, or if 14A / 14B disagree with a settled switch for 2 s | assumption | Criteria not published. S2 documents a further case: Position Error at power-up when the controller sees source voltage before the position inputs, cleared by a full power-down and re-energization. The bench does not reproduce that case (see the limits). |
| 9 | After either alarm the controller keeps SE / ER as commanded and does not retry by itself | assumption | No source confirms an automatic retry after a failed transfer. The guide only restarts Feature 2B when Emergency becomes unacceptable during 2B. |
| 10 | Generator start: rated voltage 10 s after the start signal (2 s cranking, linear in between); Emergency accepted at 90 % pickup, about 9.2 s after the signal | documented | Guide: Emergency usually accepted about 10 s after NR drops. S1, S3: in the transfer test the engine starts and runs within 15 s. The 2 s / 8 s split of the curve is ours. |
| 11 | Mechanism: 0.08 s travel (open transition), top dead center at half travel | supported | S5: Series 300 open transition switches transfer loads in under 100 ms (a brochure figure for load transfer, not a measured travel time of this frame). Changed from 0.15 s on 2026-10-31 (D35). |
| 11a | The coil operates above 70 % of nominal voltage across A-B; one operation per energization (a coil that stays energized holds the plunger); released before top dead center the mechanism falls back | assumption | No source. |
| 12 | Coil burnout chain: cut-off contacts 8-9 and 71-72 that do not open at top dead center keep the coil energized; it burns open after 30 s; a new coil burns again until the cut-off is fixed; a jammed mechanism also burns the coil | supported (risk), assumption (30 s) | S4: the coil control contacts cut off power to the solenoid, and bad cut-off timing "may lead to possible coil overheating and switch failure". S5: the operator draws power from the destination source, as modelled. The 30 s burn time is ours. |
| 13 | With both sources isolated the switch can be operated manually for a check: a jammed mechanism does not move, a cut-off contact that does not open still reads closed at the far position | documented | S1, S3: operate the manual handle only with both sources disconnected and proven dead; the mechanism must move smoothly. The policy matches (approval tier, isolated only, never under load). S3 also says to relubricate the operator when the TS coil is replaced: the replace_coil result carries that recommendation. |
| 14 | UPS autonomy 10 minutes and 30 s of virtual time per reading or action | assumption | Simulation parameters, not ASCO data. |
| 15 | Frequency is not simulated: a source with voltage is at nominal frequency | assumption | See the limits: S3's troubleshooting checks the generator frequency (at least 57 Hz) and the generator output breaker. |

## Agent action limits (S2)

Generated from `src/probeforge/ats/policy.py` (`RULES`); a test checks that this table matches the code. Tiers:
allowed; approval (a human approves); strong approval (a second, explicit approval); never (blocked whatever the
reason). Every reading or action costs 30 s of virtual time (assumption 14).

| Action | Tier | Condition |
|---|---|---|
| read_panel, read_event_log, read_metering, read_position_indicator, wait, get_schematic, update_hypotheses | allowed | always |
| measure_voltage | allowed | always (also to prove a circuit dead after isolation) |
| measure_resistance | allowed | only with both sources isolated and locked out, otherwise blocked |
| isolate_sources (open 52U, lock out the generator) | approval | while the load is not powered (lockout / tagout is a formal procedure) |
| isolate_sources | strong approval | while the load is powered: isolation de-energizes it; the policy states that fact in the request shown to the approver |
| restore_sources | allowed | before any Transfer Failure or Position Error |
| restore_sources | strong approval | after a Transfer Failure or Position Error: the controller restarts its sequence, a repeat transfer attempt |
| manual_operation_check | approval | only with both sources isolated and locked out |
| manual_operation_check | never | with any source not isolated (manual operation under load) |
| repeat_transfer_attempt | strong approval | after a Transfer Failure or Position Error; blocked otherwise |
| replace_coil, repair_wire, repair_connector, replace_cutoff_contact, adjust_cutoff_contact, replace_controller | approval | only with both sources isolated and locked out |
| the same replacement again | strong approval | after a Transfer Failure or Position Error that followed the first one |
| bypass_interlock, parallel_sources, operate_handle_under_load | never | always blocked |
| submit_diagnosis | allowed | with a confidence and evidence citing executed observation steps |
| any strong approval request | strong approval | refused before it reaches the human unless it has a reason and cites at least one executed instrument reading (evidence_steps) |

Assumed with the policy:

| # | Assumption | Status | Source and note |
|---|---|---|---|
| 16 | Re-energizing after isolation: the controller powers up (alarms clear, the event log is kept), reads the position contacts 14A / 14B and resumes from that position, so a restart alone never raises an alarm. On Normal it runs its automatic sequence, so restoring the sources after a Transfer Failure is a repeat transfer attempt; on Emergency it stays there (ER energized, engine start signal given; with Normal acceptable the documented retransfer follows); with no valid position (neither or both contacts) it shows "Switch Position Unknown" and raises Position Error | supported (power cycle, position at power-up), assumption (Transfer Failure) | S2: a power cycle clears a power-up Position Error, which the controller raises when it cannot read a valid position. Restart after a Transfer Failure: no source. Changed on 2026-10-31 (D36). |
| 17 | A repeated transfer command drops ER and energizes it again: a new operation of the TS coil | assumption | The documented way to repeat a transfer under control is the Transfer Test (S1, S3: test button, engine start, transfer, retransfer after the test delay, cooldown); repeat_transfer_attempt stands for it in the bench. |
| 18 | Isolation means 52U opened and the generator locked out (52U is not a fault location, decision D23) | documented | S1, S3: both sources disconnected before working on the switch. |
| 19 | The mechanism has a position indicator read with read_position_indicator (allowed tier, a reading like any other); the engineer in the UI sees it only after checking it | assumption | Not shown in our two documents; added for equal information between agent and engineer (D31). |

## Known limits of the bench

- **Coil resistance reading.** measure_resistance across TS A-B returns a linear 30 ohm, as if the meter reached the
  coil winding. On the real solenoid assembly A and B are the AC terminals of the bridge rectifier CR (978741 sheet 3),
  so a handheld ohmmeter reads through two diode junctions in series with the coil: depending on its test voltage it
  shows a high or open reading, and diode mode shows junction drops, not the winding. A burnt or open coil still reads
  open on both. Assumption 1 is a placeholder.
- **Power-up Position Error (S2) is partly reproduced.** At power-up the bench reads the position contacts at once;
  with no valid position it raises Position Error ("Switch Position Unknown"). The retrofit case of S2, where the
  position inputs are read only after the source voltage, is not modelled as a separate timing effect.
- **Generator not accepted.** A real "generator running but not accepted" case can be under-frequency (S3: at least
  57 Hz) or an open generator output breaker; the bench models neither (frequency is not simulated, assumption 15).
- **Readings are steady-state.** Every reading is a steady-state value taken after the 30 s action time, so a healthy
  coil pulse (under 0.1 s) never shows up, as with a handheld meter; the reading during a repeated transfer command is
  taken 1 s after the command.

## Documented but not modelled

Customer auxiliary contacts 14A (12-13, 31-32) and 14B (10-11, 29-30), option relay OP1, external Features 17 and 6B,
relay expansion modules 18RX / 18RX1, load current metering 23GB, RS-485 communications, strip heater (44G): not wired
on this unit or not relevant to the diagnosis.

## Fault catalog and twins (S1)

`src/probeforge/ats/faults.py`: 118 single faults (wires and pins open; TS main, cut-off and auxiliary contacts and
controller relay contacts stuck open or stuck closed; the solenoid open or burnt; a controller input failed; the
mechanism jammed). In the outage scenario 51 are visible on the controller panel, 17 give exactly the same readings as
a healthy switch everywhere (normal-side parts that only matter on retransfer, the redundant engine-start path), and
the rest need measurements. The only observational twins (`src/probeforge/ats/ambiguity.py`) are physically justified:
parallel engine-start contacts (TS 14B and NR NC), coil open versus burnt open, and the series SE / ER contacts inside
the controller (no probe access between them, so they are one controller-output fault). The controller's metering
screen (guide page 7) is part of the observations; it shows which emergency phase a sensing fault affects.
