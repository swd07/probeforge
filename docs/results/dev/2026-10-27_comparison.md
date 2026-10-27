# [dev] Agent vs baseline, 2026-10-27

Agent: muse-spark-1.3, reasoning effort low. Baseline: deterministic golden-twin half-split (src/probeforge/baseline/).
Holdout: 30 random visible faults + 10 random latent faults (seed 2026), none of the 8 hand-written scenarios.
For latent faults insufficient_information counts as correct.

"Justified" adds cases where the true fault is an observational twin of another fault (every observation the tools can make is
identical, checked by simulation in src/probeforge/eval/ambiguity.py) and the answer was insufficient_information or named the twin.
"Confidently wrong" is a submitted diagnosis that is neither correct nor justified.

v1 = first run. v2 = after three loop changes made between the runs: tool calls the model wrote as text markup are recovered,
the agent is told its turn budget and warned 5 and 2 turns before the end, and the task framing no longer claims a visible fault.
The prompt was not tuned on holdout cases; the v1 -> v2 changes target loop failures seen on both sets.

Caveat: the baseline rules were debugged against the full list of 91 faults, which includes the holdout faults, so the baseline had
a look at the test set that the agent prompt did not.

## Headline

- Holdout visible: agent 25/30 (28/30 justified) vs baseline 22/30 (24/30). Latent: both 10/10 (agent v1 1/10).
- Confidently wrong on the holdout: agent v2 1, baseline 4. The agent prefers insufficient_information when it cannot separate hypotheses.
- Measurements per case: agent 6.9, baseline 10.3 on the holdout (baseline falls back to an exhaustive resistance sweep when its
  rules run out); on s01-s08 the baseline is leaner (4.0 vs 6.0).
- Redundant measurements (same net pair, aliases resolved, same circuit state): agent 8 over 40 cases, baseline 28.
- Cost: agent about $0.09 per holdout case and $0.06 per scenario, 40 to 80 s per case (8 cases run in parallel). Baseline: free and instant.
- Variance (s01-s08 x3): 7 of 8 scenarios solved 3/3; s06 only 1/3 in v2 (0/3 in v1). Measurements per run vary up to 4x for the same scenario.

## Failure analysis (every case that was not correct)

Agent v2, holdout:
- h10, h13 (welded start button or welded self-hold contact): the true fault shorts the same two nets as its twin
  (SB3 13-14 vs KM2 13-14, SB2 13-14 vs KM1 13-14). No measurement without disconnecting wires can separate them. The agent said so
  (insufficient_information). Justified.
- h19 (KT coil short): blows FU1 on start; at rest the KT coil and the KM3 coil sit on the same nets through closed NC contacts, so
  "KT short" and "KM3 short" read identically. Justified.
- h26 (KM1 main pole 1-2 open): the agent narrowed it to KM1 1-2 or KM3 3-4 and knew a live measurement would separate them, but it had
  let the motor hum until the thermal relay tripped. Re-applying power then needs human approval, which batch mode denies, so it
  answered insufficient_information. Honest, and solvable with a human in the loop; the strategic error was not measuring live before the trip.
- h30 (KM4 pole 5-6 welded): the only confidently wrong answer. With the star point tied to a phase through the welded pole, the simulator
  reports the motor as "stopped" during the star stage (a modelling simplification), which looks exactly like a star contactor that does not
  close. The agent concluded KM3 1-2 stuck open. Part simulator gap, part agent error (its own reading "star point floats at 230 V" pointed
  at a phase reaching the star point, which an open KM3 pole would not cause).

Agent v2, s01-s08 x3:
- s06_r1, s06_r3 (KT coil open, diagnosed "KT stuck"): the agent measured 230 V across the KT coil and read it as "coil energized, timer
  works but never switches". Voltage present does not prove the coil is intact; only the ohmmeter separates an open coil from a stuck timer.
  In s06_r2 it took that reading and reasoned exactly right ("550 ohm equals KM3 coil alone; stuck would give about 483 ohm"). Not patched in
  the prompt on purpose, to avoid tuning to the dev set.

Agent v1 only (fixed in v2):
- 9 latent faults and s02_r2, s03_r2, h30 hit the 30-turn cap. Two causes: Muse Spark sometimes writes submit_diagnosis as text markup
  (<atem:function_calls><atem:invoke name="default.submit_diagnosis">...) instead of a native tool call and repeats it after every nudge;
  and with no budget awareness it measured one point per turn forever on faults with no symptom. v2 recovers text tool calls (4 times
  in the v2 holdout run) and warns about the budget; all 10 latent faults then end in insufficient_information.

Baseline, holdout:
- h10, h13, h25 (welded contacts or a welded contactor): its rules only handle missing voltage; unexpected energization falls through
  to an exhaustive resistance sweep, whose first mismatch is a parallel path, not the fault (it named KM1 13-14 or a "short" KM1 coil).
- h18 (KM3 coil open): the half-split ends at KM1 43-44 because the healthy twin path it follows goes through it; its pull-in check
  did not apply because the located part belongs to a different contactor. Confidently wrong.
- h19: named the observational twin (KM3 coil short). Justified by luck: a coin flip between two identical faults.
- h06 (Stop contact welded), h09 (KM3 pole open): no rule matches and the sweep finds nothing at rest; insufficient_information.
- h02 (KM4 pole open): insufficient_information; it is a twin of the other two KM4 poles, so justified.

## Tables

| Run | Visible correct | Visible correct or justified | Latent correct | Confidently wrong | Visible not diagnosed | Meas per case | Redundant | Evidence F/I | Policy blocks | Cost $ per case | Seconds per case |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Agent v2, holdout 40 | 25/30 | 28/30 | 10/10 | 1 | 4 | 6.9 | 8 | 91/110 | 2 | 0.092 | 77.5 |
| Agent v1, holdout 40 | 25/30 | 27/30 | 1/10 | 0 | 5 | 8.2 | 14 | 55/79 | 0 | 0.096 | 82.5 |
| Baseline, holdout 40 | 22/30 | 24/30 | 10/10 | 4 | 3 | 10.3 | 28 | 23/146 | 0 | 0.000 | 0.0 |
| Agent v2, s01-s08 x3 | 22/24 | 22/24 | - | 2 | 0 | 6.0 | 9 | 44/68 | 1 | 0.055 | 40.7 |
| Agent v1, s01-s08 x3 | 19/24 | 19/24 | - | 3 | 2 | 5.7 | 9 | 43/65 | 0 | 0.050 | 37.4 |
| Baseline, s01-s08 | 8/8 | 8/8 | - | 0 | 0 | 4.0 | 4 | 9/26 | 0 | 0.000 | 0.0 |

### Not correct: Agent v2, holdout 40

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| h10 | KM2:13-14 stuck_closed | insufficient_information | SB3:13-14 stuck_closed | yes |
| h13 | SB2:13-14 stuck_closed | insufficient_information | KM1:13-14 stuck_closed | yes |
| h19 | KT:A1-A2 short | insufficient_information | KM3:A1-A2 short | yes |
| h26 | KM1:1-2 stuck_open | insufficient_information | - | no |
| h30 | KM4:5-6 stuck_closed | KM3:1-2 stuck_open | - | no |

### Not correct: Agent v1, holdout 40

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| h10 | KM2:13-14 stuck_closed | insufficient_information | SB3:13-14 stuck_closed | yes |
| h13 | SB2:13-14 stuck_closed | insufficient_information | KM1:13-14 stuck_closed | yes |
| h25 | KM1 welded | insufficient_information | - | no |
| h26 | KM1:1-2 stuck_open | insufficient_information | - | no |
| h30 | KM4:5-6 stuck_closed | no_diagnosis | - | no |
| l01 | KK1:95-96 stuck_closed | no_diagnosis | KM1:21-22 stuck_closed, KM2:21-22 stuck_closed, KM3:21-22 stuck_closed, KM4:21-22 stuck_closed, KK1:97-98 stuck_open | no |
| l02 | KM4:21-22 stuck_closed | no_diagnosis | KM1:21-22 stuck_closed, KM2:21-22 stuck_closed, KM3:21-22 stuck_closed, KK1:97-98 stuck_open, KK1:95-96 stuck_closed | no |
| l03 | KM3:3-4 stuck_closed | no_diagnosis | - | no |
| l05 | KM2:21-22 stuck_closed | no_diagnosis | KM1:21-22 stuck_closed, KM3:21-22 stuck_closed, KM4:21-22 stuck_closed, KK1:97-98 stuck_open, KK1:95-96 stuck_closed | no |
| l06 | KM2:3-4 stuck_closed | no_diagnosis | KM1:3-4 stuck_closed | no |
| l07 | KM3:1-2 stuck_closed | no_diagnosis | - | no |
| l08 | KM2:43-44 stuck_closed | no_diagnosis | KM1:43-44 stuck_closed | no |
| l09 | KM1:21-22 stuck_closed | no_diagnosis | KM2:21-22 stuck_closed, KM3:21-22 stuck_closed, KM4:21-22 stuck_closed, KK1:97-98 stuck_open, KK1:95-96 stuck_closed | no |
| l10 | KM3:5-6 stuck_closed | no_diagnosis | - | no |

### Not correct: Baseline, holdout 40

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| h02 | KM4:1-2 stuck_open | insufficient_information | KM4:3-4 stuck_open, KM4:5-6 stuck_open | yes |
| h06 | SB1:11-12 stuck_closed | insufficient_information | - | no |
| h09 | KM3:5-6 stuck_open | insufficient_information | - | no |
| h10 | KM2:13-14 stuck_closed | KM1:13-14 stuck_closed | SB3:13-14 stuck_closed | no |
| h13 | SB2:13-14 stuck_closed | KM1:A1-A2 short | KM1:13-14 stuck_closed | no |
| h18 | KM3:A1-A2 open | KM1:43-44 stuck_open | - | no |
| h19 | KT:A1-A2 short | KM3:A1-A2 short | KM3:A1-A2 short | yes |
| h25 | KM1 welded | KM1:A1-A2 short | - | no |

### Variance: Agent v2, s01-s08 x3

| Scenario | Correct runs | Measurements per run | Mean | Cost $ mean | Seconds mean |
|---|---|---|---|---|---|
| s01 | 3/3 | 4, 4, 6 | 4.7 | 0.040 | 17.7 |
| s02 | 3/3 | 7, 6, 11 | 8.0 | 0.046 | 34.6 |
| s03 | 3/3 | 3, 8, 3 | 4.7 | 0.049 | 27.7 |
| s04 | 3/3 | 8, 7, 4 | 6.3 | 0.040 | 30.8 |
| s05 | 3/3 | 3, 1, 0 | 1.3 | 0.048 | 56.6 |
| s06 | 1/3 | 6, 8, 9 | 7.7 | 0.056 | 42.7 |
| s07 | 3/3 | 8, 9, 7 | 8.0 | 0.093 | 70.3 |
| s08 | 3/3 | 3, 12, 7 | 7.3 | 0.065 | 44.9 |

### Not correct: Agent v2, s01-s08 x3

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| s06_r1 | KT:A1-A2 open | KT stuck | - | no |
| s06_r3 | KT:A1-A2 open | KT stuck | - | no |

### Variance: Agent v1, s01-s08 x3

| Scenario | Correct runs | Measurements per run | Mean | Cost $ mean | Seconds mean |
|---|---|---|---|---|---|
| s01 | 3/3 | 5, 4, 3 | 4.0 | 0.040 | 18.8 |
| s02 | 2/3 | 8, 11, 4 | 7.7 | 0.076 | 49.2 |
| s03 | 2/3 | 3, 11, 6 | 6.7 | 0.073 | 43.2 |
| s04 | 3/3 | 4, 4, 10 | 6.0 | 0.039 | 30.5 |
| s05 | 3/3 | 2, 0, 0 | 0.7 | 0.036 | 38.9 |
| s06 | 0/3 | 9, 6, 4 | 6.3 | 0.044 | 39.5 |
| s07 | 3/3 | 6, 9, 9 | 8.0 | 0.054 | 48.3 |
| s08 | 3/3 | 5, 5, 9 | 6.3 | 0.041 | 30.8 |

### Not correct: Agent v1, s01-s08 x3

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| s06_r1 | KT:A1-A2 open | KT stuck | - | no |
| s02_r2 | SB1:11-12 stuck_open | no_diagnosis | - | no |
| s03_r2 | KK1 tripped | no_diagnosis | - | no |
| s06_r2 | KT:A1-A2 open | KT stuck | - | no |
| s06_r3 | KT:A1-A2 open | KT stuck | - | no |
