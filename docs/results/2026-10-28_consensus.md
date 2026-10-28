# Self-consistency flags and the no-flags ablation (2026-10-28, dev)

Dev results (the hybrid was changed after its clean-holdout results had been seen; the final unseen test will be
a second circuit). All scores at pole level; "confidently wrong" names a wrong component, mode or part.

## What was added

- **Self-consistency flags** (`src/probeforge/hybrid/consensus.py`): several reads of the same schematic; every
  terminal whose connections differ between the reads is uncertain. Disagreeing terminals that share a net in any
  read form one region. These regions are added to Muse Spark's own flags and feed the joint wiring variants. The
  model netlist is the read that agrees most with the others (share of connection pairs in common).
  `read_consensus()` does this live (3 reads at medium effort, about $0.20; the UI's live read now uses it);
  `scripts/consensus_read.py` builds it from saved replies without API calls.
- **No-flags ablation**: `run_scenarios.py --flags none` runs the hybrid on the same transcription with no
  uncertain regions, so no joint wiring variants (`--extra-flags FILE` adds regions from another file).

## Test on the existing photo reads (no new API calls for the reads)

Photo reads 1, 2 and 3 are three reads of the same photo. Read 3 agrees most with the others (agreement
0.844 / 0.893 with reads 1 and 2) and becomes the model. 3 disagreement regions: the KM1/KM2 supply crossover
(FU2, KM1, KM2 input pins), the KM1/KM2 output ties (KK1, KM1, KM2), and the star/delta links (KM3, KM4, M1).
Coverage of the terminals of wrongly read nets (checked against the truth afterwards):

| Read | Wrong nets | Covered by its own flags | Own + disagreement flags |
|---|---|---|---|
| 1 | 6 | 12/18 | 18/18 |
| 2 | 7 | 17/21 | 21/21 |
| 3 (model) | 6 | 18/18 | 18/18 |

## Results (clean holdout faults, 38 visible + 5 latent; latent 5/5 everywhere)

| Read | Flags | Repair | Pole level | Component level | Pole left open | Confidently wrong | $ per case |
|---|---|---|---|---|---|---|---|
| 3 | none | no | 26/38 | 30/38 | 2 | 2 | 0 |
| 1 | none | no | 26/38 | 30/38 | 2 | 2 | 0 |
| 3 | Muse only | no | 32/38 | 33/38 | 1 | 0 | 0 |
| 1 | Muse only | no | 28/38 | 33/38 | 1 | 4 | 0 |
| 3 | Muse only | yes | 32/38 | 33/38 | 1 | 0 | 0.006 |
| 1 | Muse only | yes | 28/38 | 33/38 | 1 | 4 | 0.006 |
| **consensus (3)** | **Muse + disagreement** | no | **32/38** | 33/38 | 1 | **0** | 0 |
| **consensus (3)** | **Muse + disagreement** | yes | **32/38** | 33/38 | 1 | **0** | 0.006 |
| 1 (extra) | Muse + disagreement | no | 32/38 | 33/38 | 1 | 0 | 0 |

- **Without flags** both reads give 26/38 with 2 confidently wrong (the KM3 star poles c24, c25) and three
  handovers: this replaces the old "without Muse Spark" comparison, which used the PNG run-2 read.
- **Joint wiring variants** add 6 cases on read 3 (26 to 32) and 2 on read 1 (26 to 28), and remove the
  confidently wrong answers where the flags cover the misread wiring.
- **Disagreement flags** close the gap of the weaker read: read 1 with them reaches the same 32/38 and 0 confidently
  wrong as read 3 (its own flags had missed one phase of the KM2 crossover and the KM3 star wiring). On read 3,
  whose own flags already covered every error, they change nothing, so the consensus result equals read 3 with its
  own flags.
- **Repair** is never called in these runs: every conflict (3 per run) is explained by a wiring variant first.
- Smoke test first (consensus read, c06, c15, c18, c24, c25, with repair): 4 right at pole level, c06 pole left
  open, $0.03.

## Cost

Smoke test $0.03, full run with repair $0.25; reads, ablations and the no-repair runs free. Spend $44.45 of $130.

Raw: runs/20261028_224927 and _224929 (no flags), _221921 and _221923 (Muse flags, no repair), _223104 and _223106
(Muse flags, repair), _224931 (consensus, no repair), _230137 (consensus, repair), _224933 (read 1 + disagreement),
_225910 (smoke test).

## Full summary

| Run | Visible correct (pole) | incl. justified | Component level | Latent correct | Confidently wrong | Pole left open | Visible not diagnosed | Meas per case | Redundant | Evidence F/I | Policy blocks | Approvals asked/denied | Missing hyp. updates | Text tool calls | Cost $ per case | Seconds per case |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Read 3, no flags, no repair | 26/38 | 29/38 | 30/38 | 5/5 | 2 | 2 | 8 | 2.8 | 0 | 82/113 | 0 | 0/0 | 0 | 0 | 0.000 | 25.8 |
| Read 1, no flags, no repair | 26/38 | 29/38 | 30/38 | 5/5 | 2 | 2 | 8 | 2.8 | 0 | 82/113 | 0 | 0/0 | 0 | 0 | 0.000 | 25.6 |
| Read 3, Muse flags, no repair | 32/38 | 35/38 | 33/38 | 5/5 | 0 | 1 | 5 | 3.4 | 0 | 75/137 | 0 | 0/0 | 0 | 0 | 0.000 | 73.2 |
| Read 1, Muse flags, no repair | 28/38 | 31/38 | 33/38 | 5/5 | 4 | 1 | 5 | 3.3 | 0 | 74/132 | 0 | 0/0 | 0 | 0 | 0.000 | 64.7 |
| Read 3, Muse flags + repair | 32/38 | 35/38 | 33/38 | 5/5 | 0 | 1 | 5 | 3.4 | 0 | 75/137 | 0 | 0/0 | 0 | 0 | 0.006 | 78.0 |
| Read 1, Muse flags + repair | 28/38 | 31/38 | 33/38 | 5/5 | 4 | 1 | 5 | 3.3 | 0 | 74/132 | 0 | 0/0 | 0 | 0 | 0.006 | 69.9 |
| Consensus (read 3), Muse + disagreement flags, no repair | 32/38 | 35/38 | 33/38 | 5/5 | 0 | 1 | 5 | 3.4 | 0 | 75/137 | 0 | 0/0 | 0 | 0 | 0.000 | 51.4 |
| Consensus (read 3), Muse + disagreement flags + repair | 32/38 | 35/38 | 33/38 | 5/5 | 0 | 1 | 5 | 3.4 | 0 | 75/137 | 0 | 0/0 | 0 | 0 | 0.006 | 90.9 |
| Read 1, Muse + disagreement flags, no repair (extra) | 32/38 | 35/38 | 33/38 | 5/5 | 0 | 1 | 5 | 3.3 | 0 | 75/137 | 0 | 0/0 | 0 | 0 | 0.000 | 42.0 |

### Not correct: Read 3, no flags, no repair

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
| c29 | KM4:5-6 stuck_open | KM4 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Read 1, no flags, no repair

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
| c29 | KM4:5-6 stuck_open | KM4 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Read 3, Muse flags, no repair

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c06 | KM1:3-4 stuck_open | KM1 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Read 1, Muse flags, no repair

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | insufficient_information | - | no |
| c06 | KM1:3-4 stuck_open | KM1 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c15 | KM2:1-2 stuck_closed | KM2:5-6 stuck_closed | - | no |
| c18 | KM2:5-6 stuck_closed | KM2:1-2 stuck_closed | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c24 | KM3:1-2 stuck_open | KM3:5-6 stuck_open | - | no |
| c25 | KM3:3-4 stuck_open | KM3:1-2 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Read 3, Muse flags + repair

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c06 | KM1:3-4 stuck_open | KM1 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Read 1, Muse flags + repair

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | insufficient_information | - | no |
| c06 | KM1:3-4 stuck_open | KM1 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c15 | KM2:1-2 stuck_closed | KM2:5-6 stuck_closed | - | no |
| c18 | KM2:5-6 stuck_closed | KM2:1-2 stuck_closed | - | no |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c24 | KM3:1-2 stuck_open | KM3:5-6 stuck_open | - | no |
| c25 | KM3:3-4 stuck_open | KM3:1-2 stuck_open | - | no |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Consensus (read 3), Muse + disagreement flags, no repair

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c06 | KM1:3-4 stuck_open | KM1 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Consensus (read 3), Muse + disagreement flags + repair

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c06 | KM1:3-4 stuck_open | KM1 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c08 | KM1:5-6 stuck_closed | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |

### Not correct: Read 1, Muse + disagreement flags, no repair (extra)

| Case | Expected | Answer | Observational twins | Justified |
|---|---|---|---|---|
| c05 | KM1:1-2 stuck_closed | insufficient_information | - | no |
| c06 | KM1:3-4 stuck_open | KM1 stuck_open | - | no |
| c07 | KM1:5-6 stuck_open | insufficient_information | - | no |
| c09 | KM1:13-14 stuck_closed | insufficient_information | SB2:13-14 stuck_closed | yes |
| c23 | KM3:A1-A2 short | insufficient_information | KT:A1-A2 short | yes |
| c35 | SB3:13-14 stuck_closed | insufficient_information | KM2:13-14 stuck_closed | yes |
