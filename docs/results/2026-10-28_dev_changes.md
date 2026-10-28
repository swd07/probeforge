# Hybrid changes after the clean holdout (2026-10-28, dev)

These changes were made after the hybrid's clean-holdout results had been seen, so every hybrid
number below is a **dev** result (run folders end in `_dev`, titles start with DEV). The final unseen
test will be a second circuit.

## What changed

1. **Pole-level scoring everywhere.** Correct = component, failure mode and part. The component-level
   score is kept as a column. A diagnosis with the right component and mode and no part is "pole left
   open" (not correct, not wrong). Confidently wrong = names a wrong component, mode or part. Every
   saved run was rescored from its diagnosis: [2026-10-28_pole_level.md](2026-10-28_pole_level.md).
2. **Model-uncertainty propagation** (`src/probeforge/hybrid/uncertainty.py`). If a terminal of the
   diagnosed part lies in a region the transcription flagged as uncertain, the planner builds the
   alternative wirings of that region (the terminals on one side of same-kind parts of a component,
   in every order: what a misread crossover does), replays every reading on each, and collects the
   faults that fit. If they imply another pole, the pole is dropped: "KM3 stuck_open, pole ambiguous:
   confirm wiring at <terminals>", confidence 1/number of poles. If they imply another component, the
   answer becomes insufficient_information with the same note. In the UI a human is asked which wiring
   the panel has and the pole follows from the choice; batch runs have no human.
3. **Correction acceptance rule** (`src/probeforge/hybrid/acceptance.py`). A repair proposal is
   rejected (and logged with reasons) if it changes fault-free behaviour that no reading contradicted:
   every field of a recorded reading that the current model reproduced must still be reproduced, and in
   a generic fault-free run (each start button, short and long wait, the other starts, stop) a field may
   change only if a real reading contradicted fields of its kind (each lamp; motor state, currents and
   amps together; meter readings; settling). The planner then asks again; the next prompt says why the
   proposal was rejected. Rejections count towards the limit of 3 proposals per run.
4. **Mechanical interlock symbol.** The renderer did not draw the mechanical interlocks, so no
   transcription could find them. It now draws the IEC-style symbol (dashed linkage between the two
   contactors with an inverted triangle) for every pair in `interlocks`. Note: this changes the
   schematic image the pure agent receives from now on; the agent results in the README were made with
   the old image.

## Results (clean holdout faults, pole level, dev for the hybrid rows)

| | Visible correct (pole) | incl. justified | Component level | Latent | Confidently wrong | Pole left open | Meas per case | $ per case |
|---|---|---|---|---|---|---|---|---|
| Pure agent (true netlist + image) | 30/38 | 33/38 | 30/38 | 5/5 | 4 | 0 | 8.3 | 0.068 |
| Info-gain on the true netlist | 35/38 | 38/38 | 35/38 | 5/5 | 0 | 0 | 2.6 | 0 |
| Hybrid PNG run 2, before | 25/38 | 28/38 | 29/38 | 5/5 | 2 | 2 | 3.2 | 0.066 |
| **DEV hybrid PNG run 2** | **26/38** | **29/38** | 30/38 | 5/5 | 3 | 2 | 2.9 | 0.065 |
| Hybrid photo run 3, before | 27/38 | 30/38 | 32/38 | 5/5 | 4 | 2 | 3.0 | 0.024 |
| **DEV hybrid photo run 3** | **20/38** | **23/38** | 31/38 | 5/5 | **2** | 11 | 3.0 | 0.026 |
| Hybrid photo run 1, before | 27/38 | 30/38 | 31/38 | 5/5 | 2 | 2 | 3.1 | 0.017 |
| **DEV hybrid photo run 1** | **20/38** | **23/38** | 31/38 | 5/5 | 4 | 9 | 3.0 | 0.024 |

What the changes did:

- **Wiring check.** Photo runs: it ran in 21 cases each and dropped the pole in 11 (run 3) and 9 (run 1).
  It removed the two confidently wrong KM3 star poles in run 3 (c24, c25 are now "KM3 stuck_open, pole
  ambiguous" at 33%). It also dropped poles that had been right (KM1/KM2 main poles, the KM2 13-14 vs
  43-44 aux contacts): those answers had been right by luck, because every reading fits the other
  wirings of the flagged crossover as well. In photo run 1 the KM3 star wiring was not flagged (the
  flag list names KM3 only in the control circuit), so c24 and c25 stay confidently wrong: the check
  can only be as good as the flags. PNG run 2 has no flags (it predates the flag prompt), so the check
  never runs there.
- **Acceptance rule.** 10 proposals rejected over the three runs (3, 2, 5); afterwards each was checked
  against the true netlist and all 10 would have broken the fault-free machine (healthy panel sequence
  wrong). Offline replay of the earlier runs with their recorded replies: the rule rejects 9 of 42
  recorded proposals, every one tying two supply phases or two windings together; 31 of the 33 it
  accepts give a correct fault-free run.
- **Side effect of the rule on welded main poles (c15, c18).** After a rejection the planner asks
  again; the next proposal passed the rule but explained the welded-pole readings as an open pole. These
  cases had ended as a handover or a different wrong answer before; now they are wrong in the failure
  mode (twice at 33% confidence in each photo run, once at 100% in PNG run 2, c15). This is why
  confidently wrong went up in PNG run 2 and photo run 1. The rule protects fault-free behaviour; it
  does not stop a proposal that explains the readings with the wrong fault.
- **Interlock symbol.** 3 new transcriptions of the PNG with the symbol: all 3 list both interlocks
  (before: 0 of 6 flagged transcriptions, 2 of 3 unflagged ones, probably from domain knowledge; 0 of 3
  photo transcriptions). Connections P/R 0.958, 0.901, 0.894; one run has 32 of 35 nets exact, the best
  read so far. Every wrong net was inside a flagged region in all three runs.

## Verify step counts (dev)

| | Conflicts | Proposals accepted / rejected | Rejected ones with a wrong healthy panel (truth) | Handovers | Wiring check ran / pole dropped |
|---|---|---|---|---|---|
| PNG run 2 | 34 in 31 cases | 33 / 5 | 5 | 1 | 0 / 0 |
| Photo run 3 | 3 in 3 cases | 3 / 3 | 3 | 0 | 21 / 11 |
| Photo run 1 | 3 in 3 cases | 4 / 2 | 2 | 0 | 21 / 9 |

## Incidents and cost

- First photo dev batches: the wiring check took every flagged region that mentioned the diagnosed
  component (for KM2 that pulled the lamp contact 53-54 into a region about seal-in contacts) instead of
  only regions containing a terminal of the diagnosed part. Fixed and both photo batches rerun; the
  first results are superseded (runs 20261028_210306 and _210309, not reported).
- The photo run 1 batch crashed on the spend-ledger lock (Windows reports PermissionError while
  another process deletes the lock file). Fixed (retry on PermissionError). The one unrecorded case
  (c37, an explanation call) was entered as a $0.006 estimate. A restarted batch was stopped within
  a minute when the region bug was found; it recorded nothing, and calls in flight at that moment (at
  most 8) are not in the ledger.
- Cost of this round: $7.81 (superseded batches $2.70, PNG run 2 $2.80, photo reruns $2.13,
  interlock transcriptions $0.18), plus two UI runs ($0.01). Spend $43.62 of $110.

Raw: runs/20261028_210312_hybrid_clean_dev (PNG run 2), runs/20261028_213329_hybrid_clean_dev (photo
run 3), runs/20261028_213332_hybrid_clean_dev (photo run 1), runs/20261028_210316_transcribe_flags.
