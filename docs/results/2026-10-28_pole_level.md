# Every reported run rescored at pole level (2026-10-28)

"Correct" is now pole level: component, failure mode and part (pole or contact) must match the injected fault.
"Component level" (component and failure mode, part ignored) was the definition before and is kept as a column.
"Pole left open": the right component and mode with no part named (not correct, not wrong). "Confidently
wrong": a submitted diagnosis that names a wrong component, mode or part and is not justified by an
observational twin (justified now also needs the twin's part). Every case is rescored from its saved
diagnosis by `scripts/summarize_results.py`; nothing was rerun for this table except the DEV rows.

DEV rows: the hybrid after the changes of 2026-10-28 evening (pole-level scoring, correction acceptance
rule, wiring check of flagged regions, interlock symbol), made after the clean holdout results were
seen, so they are dev results, not a holdout. Details: [2026-10-28_dev_changes.md](2026-10-28_dev_changes.md).

| Run | Visible correct (pole) | incl. justified | Component level | Latent correct | Confidently wrong | Pole left open | Visible not diagnosed | Meas per case | Redundant | Evidence F/I | Policy blocks | Approvals asked/denied | Missing hyp. updates | Text tool calls | Cost $ per case | Seconds per case |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Agent (netlist + image) | 30/38 | 33/38 | 30/38 | 5/5 | 4 | 0 | 4 | 8.3 | 17 | 105/115 | 0 | 11/11 | 79 | 1 | 0.068 | 54.5 |
| Agent, netlist only | 30/38 | 33/38 | 30/38 | 5/5 | 3 | 0 | 5 | 9.8 | 12 | 103/90 | 1 | 8/8 | 102 | 1 | 0.077 | 63.0 |
| Agent, image only | 28/38 | 31/38 | 31/38 | 5/5 | 2 | 3 | 5 | 8.7 | 18 | 113/100 | 1 | 11/11 | 108 | 1 | 0.082 | 67.8 |
| Half-split baseline | 25/38 | 25/38 | 25/38 | 5/5 | 9 | 0 | 4 | 11.0 | 29 | 26/171 | 0 | 0/0 | 0 | 0 | 0.000 | 0.0 |
| Info-gain, true netlist | 35/38 | 38/38 | 35/38 | 5/5 | 0 | 0 | 3 | 2.6 | 0 | 60/107 | 0 | 0/0 | 0 | 0 | 0.000 | 4.0 |
| Hybrid PNG run 2 (before the changes) | 25/38 | 28/38 | 29/38 | 5/5 | 2 | 2 | 9 | 3.2 | 0 | 77/120 | 0 | 0/0 | 0 | 0 | 0.066 | 98.9 |
| Hybrid PNG run 2, no repair (before) | 10/38 | 13/38 | 10/38 | 5/5 | 0 | 0 | 28 | 1.4 | 0 | 85/62 | 0 | 0/0 | 0 | 0 | 0.000 | 43.0 |
| Hybrid photo run 3 (before) | 27/38 | 30/38 | 32/38 | 5/5 | 4 | 2 | 5 | 3.0 | 0 | 86/119 | 0 | 0/0 | 0 | 0 | 0.024 | 67.7 |
| Hybrid photo run 1 (before) | 27/38 | 30/38 | 31/38 | 5/5 | 2 | 2 | 7 | 3.1 | 0 | 85/120 | 0 | 0/0 | 0 | 0 | 0.017 | 46.6 |
| DEV hybrid PNG run 2 | 26/38 | 29/38 | 30/38 | 5/5 | 3 | 2 | 7 | 2.9 | 0 | 80/116 | 0 | 0/0 | 0 | 0 | 0.065 | 118.4 |
| DEV hybrid photo run 3 | 20/38 | 23/38 | 31/38 | 5/5 | 2 | 11 | 5 | 3.0 | 0 | 85/118 | 0 | 0/0 | 0 | 0 | 0.026 | 64.0 |
| DEV hybrid photo run 1 | 20/38 | 23/38 | 31/38 | 5/5 | 4 | 9 | 5 | 3.0 | 0 | 84/121 | 0 | 0/0 | 0 | 0 | 0.024 | 62.6 |

### Not correct: Agent (netlist + image)

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c02 | QF1:5-6 open | insufficient_information | - | no |
| c05 | KM1:1-2 stuck_closed | KM2 stuck_open | - | no |
| c08 | KM1:5-6 stuck_closed | KM2:43-44 stuck_open | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c15 | KM2:1-2 stuck_closed | M1:V1-V2 short | - | no |
| c18 | KM2:5-6 stuck_closed | FU2:1-2 open | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Agent, netlist only

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c06 | KM1:3-4 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | KM2:1-2 stuck_open | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c12 | KM2 welded | insufficient_information | - | no |
| c15 | KM2:1-2 stuck_closed | FU2:1-2 open | - | no |
| c18 | KM2:5-6 stuck_closed | FU2:1-2 open | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Agent, image only

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c01 | QF1:3-4 open | insufficient_information | - | no |
| c02 | QF1:5-6 open | QF1 open | - | no |
| c04 | FU2:3-4 open | FU2 open | - | no |
| c05 | KM1:1-2 stuck_closed | KM2:43-44 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | KM2:1-2 stuck_open | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |
| c38 | M1:V1-V2 open | M1 open | - | no |

### Not correct: Half-split baseline

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | FU2:1-2 open | - | no |
| c08 | KM1:5-6 stuck_closed | FU2:1-2 open | - | no |
| c09 | KM1:13-14 stuck_closed | KM1:A1-A2 short | SB2:13-14 stuck_closed | no |
| c12 | KM2 welded | KM1:3-4 stuck_closed | - | no |
| c15 | KM2:1-2 stuck_closed | FU2:1-2 open | - | no |
| c18 | KM2:5-6 stuck_closed | FU2:1-2 open | - | no |
| c21 | KM2:53-54 stuck_closed | KM1:13-14 stuck_closed | - | no |
| c24 | KM3:1-2 stuck_open | insufficient_information | - | no |
| c25 | KM3:3-4 stuck_open | insufficient_information | - | no |
| c27 | KM4:3-4 stuck_open | insufficient_information | - | no |
| c29 | KM4:5-6 stuck_open | insufficient_information | - | no |
| c30 | KT:55-56 stuck_closed | KM3:21-22 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | KM1:13-14 stuck_closed | KM2:13-14 stuck_closed | no |

### Not correct: Info-gain, true netlist

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Hybrid PNG run 2 (before the changes)

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | insufficient_information | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c15 | KM2:1-2 stuck_closed | insufficient_information | - | no |
| c18 | KM2:5-6 stuck_closed | insufficient_information | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c24 | KM3:1-2 stuck_open | KM3:5-6 stuck_open | - | no |
| c25 | KM3:3-4 stuck_open | KM3:1-2 stuck_open | - | no |
| c27 | KM4:3-4 stuck_open | KM4 stuck_open | - | no |
| c28 | KM4:3-4 stuck_closed | insufficient_information | - | no |
| c29 | KM4:5-6 stuck_open | KM4 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Hybrid PNG run 2, no repair (before)

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | insufficient_information | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c10 | KM1:53-54 stuck_open | insufficient_information | - | no |
| c11 | KM1:21-22 stuck_open | insufficient_information | - | no |
| c12 | KM2 welded | insufficient_information | - | no |
| c13 | KM2:A1-A2 short | insufficient_information | - | no |
| c14 | KM2:1-2 stuck_open | insufficient_information | - | no |
| c15 | KM2:1-2 stuck_closed | insufficient_information | - | no |
| c16 | KM2:3-4 stuck_open | insufficient_information | - | no |
| c17 | KM2:5-6 stuck_open | insufficient_information | - | no |
| c18 | KM2:5-6 stuck_closed | insufficient_information | - | no |
| c19 | KM2:13-14 stuck_open | insufficient_information | - | no |
| c20 | KM2:43-44 stuck_open | insufficient_information | - | no |
| c22 | KM2:21-22 stuck_open | insufficient_information | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c24 | KM3:1-2 stuck_open | insufficient_information | - | no |
| c25 | KM3:3-4 stuck_open | insufficient_information | - | no |
| c26 | KM4:1-2 stuck_closed | insufficient_information | - | no |
| c27 | KM4:3-4 stuck_open | insufficient_information | - | no |
| c28 | KM4:3-4 stuck_closed | insufficient_information | - | no |
| c29 | KM4:5-6 stuck_open | insufficient_information | - | no |
| c34 | SB2:13-14 stuck_open | insufficient_information | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |
| c36 | HL1:X1-X2 open | insufficient_information | - | no |
| c37 | M1:U1-U2 open | insufficient_information | - | no |
| c38 | M1:V1-V2 open | insufficient_information | - | no |

### Not correct: Hybrid photo run 3 (before)

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c15 | KM2:1-2 stuck_closed | KM1:1-2 stuck_closed | - | no |
| c18 | KM2:5-6 stuck_closed | KM2:3-4 stuck_closed | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c24 | KM3:1-2 stuck_open | KM3:5-6 stuck_open | - | no |
| c25 | KM3:3-4 stuck_open | KM3:1-2 stuck_open | - | no |
| c27 | KM4:3-4 stuck_open | KM4 stuck_open | - | no |
| c29 | KM4:5-6 stuck_open | KM4 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Hybrid photo run 1 (before)

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | insufficient_information | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c15 | KM2:1-2 stuck_closed | insufficient_information | - | no |
| c18 | KM2:5-6 stuck_closed | insufficient_information | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c24 | KM3:1-2 stuck_open | KM3:5-6 stuck_open | - | no |
| c25 | KM3:3-4 stuck_open | KM3:1-2 stuck_open | - | no |
| c27 | KM4:3-4 stuck_open | KM4 stuck_open | - | no |
| c29 | KM4:5-6 stuck_open | KM4 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: DEV hybrid PNG run 2

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | insufficient_information | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c15 | KM2:1-2 stuck_closed | KM2:5-6 stuck_open | - | no |
| c18 | KM2:5-6 stuck_closed | insufficient_information | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c24 | KM3:1-2 stuck_open | KM3:5-6 stuck_open | - | no |
| c25 | KM3:3-4 stuck_open | KM3:1-2 stuck_open | - | no |
| c27 | KM4:3-4 stuck_open | KM4 stuck_open | - | no |
| c29 | KM4:5-6 stuck_open | KM4 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: DEV hybrid photo run 3

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | KM1 stuck_closed | - | no |
| c06 | KM1:3-4 stuck_open | KM1 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c14 | KM2:1-2 stuck_open | KM2 stuck_open | - | no |
| c15 | KM2:1-2 stuck_closed | KM2 stuck_open | - | no |
| c16 | KM2:3-4 stuck_open | KM2 stuck_open | - | no |
| c17 | KM2:5-6 stuck_open | KM2 stuck_open | - | no |
| c18 | KM2:5-6 stuck_closed | KM2 stuck_open | - | no |
| c19 | KM2:13-14 stuck_open | KM2 stuck_open | - | no |
| c20 | KM2:43-44 stuck_open | KM2 stuck_open | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c24 | KM3:1-2 stuck_open | KM3 stuck_open | - | no |
| c25 | KM3:3-4 stuck_open | KM3 stuck_open | - | no |
| c27 | KM4:3-4 stuck_open | KM4 stuck_open | - | no |
| c29 | KM4:5-6 stuck_open | KM4 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: DEV hybrid photo run 1

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | insufficient_information | - | no |
| c06 | KM1:3-4 stuck_open | KM1 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | KM1 stuck_closed | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c14 | KM2:1-2 stuck_open | KM2 stuck_open | - | no |
| c15 | KM2:1-2 stuck_closed | KM2 stuck_open | - | no |
| c16 | KM2:3-4 stuck_open | KM2 stuck_open | - | no |
| c17 | KM2:5-6 stuck_open | KM2 stuck_open | - | no |
| c18 | KM2:5-6 stuck_closed | KM2 stuck_open | - | no |
| c19 | KM2:13-14 stuck_open | KM2 stuck_open | - | no |
| c20 | KM2:43-44 stuck_open | KM2 stuck_open | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c24 | KM3:1-2 stuck_open | KM3:5-6 stuck_open | - | no |
| c25 | KM3:3-4 stuck_open | KM3:1-2 stuck_open | - | no |
| c27 | KM4:3-4 stuck_open | KM4 stuck_open | - | no |
| c29 | KM4:5-6 stuck_open | KM4 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |
