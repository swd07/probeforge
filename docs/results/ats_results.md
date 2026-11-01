# ATS bench results (ASCO Series 300 Group G, drawing 978741)

S5 holdout, run once on 2026-10-31 after the freeze (D45), on the code tagged
[`holdout-2026-10-31`](https://github.com/swd07/probeforge/tree/holdout-2026-10-31) (commit c54809b). Three defects in frozen code were fixed afterwards and are listed under
"Post-holdout fixes" below; the holdout numbers are those of the tagged code. Dev results sit next to it for reference
and are never presented as holdout. Machine-readable: [ats_results.json](ats_results.json); per-case traces in
[results/runs/20261031_123544_ats_holdout/](../../results/runs/20261031_123544_ats_holdout/) (all cited runs:
[results/runs/](../../results/runs/README.md)).

## What was run

- **Holdout list:** 28 cases made by seed 20261031 from the bench's fault catalog after the freeze, committed with
  its sha256 (`9f570d3c...c39e`, commit c54809b) before the run:
  [scenarios/ats_holdout/holdout.yaml](../../scenarios/ats_holdout/holdout.yaml). It holds 24 single faults visible on
  the controller panel during the outage, the other side of the burnout chain (TS 6-7 and TS 69-70 stuck closed, the
  coil burnt), and 3 latent faults (no symptom during the outage).
- **Exclusions:** every dev fault, the 3 observational twins of the dev cases, and TS:4-20 stuck_open (a UI run at
  10:38); see "Faults seen in the UI" below.
- **Diagnosticians:**
  - **Agent:** Muse Spark 1.3, Chat Completions, low reasoning effort.
  - **Hybrid v2:** the default saved transcription of the drawing, repair and explanation as in the UI.
  - **Info-gain baseline:** the same planner on the true netlist, no model, a ceiling for the planner.
- **Run rules:** batch approvals (approval tier approved, strong approval denied), one run, no reruns. The first 5
  cases were the smoke test, checked for technical failures only: none. Before starting, the run checked the list
  against its hash and the commit, and the 13 frozen fingerprints against those stored in the list.
- **Cost:** $3.54 of the $6 cap; wall time 12.6 min with 5 cases in parallel.
- **Latent rule, fixed in the list before the run:** correct only with "insufficient information"; any confident
  diagnosis counts as confidently wrong.

## Post-holdout fixes (D47, 2026-11-01)

An external review found three defects in frozen code after the holdout run. They were fixed in place, with new
fingerprints for the toolbox, the policy and the explanation step; the code that produced the holdout numbers stays
reachable as the tag [`holdout-2026-10-31`](https://github.com/swd07/probeforge/tree/holdout-2026-10-31).

1. **Powered-load isolation could not be requested in a schema-valid way.** The policy required `evidence_steps` for
   it, but the `isolate_sources` schema had no such field. In the recorded runs the agent sent it anyway, as a JSON
   string such as `"[1, 2, 4]"`, 15 times; all were refused. The field is now in the schema.
2. **Caller arguments could count as instrument evidence.** Any executed call with a `readings` argument counted as a
   meter reading for the strong-approval evidence rule. Evidence now comes from what executed: the meter tools, and the
   manual check or repeat transfer only when their result holds readings.
3. **The explanation check accepted repair wording without isolation first.** Code now puts one fixed sentence before
   every action ("Before any work: open 52U, lock out and tag the generator, and prove both sources dead at the work
   point with a voltmeter."), and the check rejects a repair instruction before it, evidence citing steps that did not
   run, and a fixed list of unsafe wordings. An audit then passed that list with synonyms and with text placed before
   the sentence; D50 widened it (bypassing, jumpers, paralleling sources, skipping the lockout or isolation anywhere in
   the text; energized work in the action; re-energizing before a repair) and narrowed negation to its own clause. It
   is a word list, not a safety review.

With them, the toolbox rejects arguments outside each tool's schema (`submit_diagnosis` gained an optional `note`,
which the planner already sent).

- **Offline proof (no model calls):** Hybrid v2 on both saved transcriptions and the baseline, on the 12 dev cases and
  the 28 holdout cases: tool logs and diagnoses identical before and after the fixes (120 of 120), and identical to the
  traces recorded in the holdout run (56 of 56) ([results/identity/](../../results/identity/)).
- **The agent was not re-run.** Its holdout numbers come from the tagged code. A post-fix smoke check on 5 dev cases
  ran without technical errors; it is a check, not a result.
- **Explanations after the fix (12 dev cases):** 0 of 12 failed the check, 10 model texts and 2 templates, the
  isolation sentence in all 12; diagnoses identical to the D42 run.
- **Freeze scope:** the fingerprints cover the listed components, not every dependency (for example `sim/netlist.py`
  and the bytes of the drawing crops).
- **Known limitations not fixed (frozen code):** the planner's cache key ignores resistance values, so two netlists
  that differ only in a value share cached benches; two identical readings in a row are not counted as redundant.

## Results, dev and holdout side by side

| | Agent dev | Agent holdout | Hybrid v2 dev | Hybrid v2 holdout | Baseline dev | Baseline holdout |
|---|---|---|---|---|---|---|
| Cases | 12 | 28 | 12 | 28 | 12 | 28 |
| Part-level correct | 10/12 | 17/28 | 10/12 | 18/28 | 10/12 | 18/28 |
| Justified (names a twin no reading separates) | 1/12 | 0/28 | 1/12 | 0/28 | 1/12 | 0/28 |
| Confidently wrong | 0/12 | **3/28** | 0/12 | 0/28 | 0/12 | 0/28 |
| Insufficient information | 2/12 | 11/28 | 2/12 | 13/28 | 2/12 | 13/28 |
| Explanation check passed (model texts + templates) | n/a | n/a | 12/12 (10 + 2) | 28/28 (15 + 13) | n/a | n/a |
| UPS left at diagnosis, median | n/a | 7:38 | 7:30 | 9:08 | 7:30 | 8:53 |
| Any diagnosis before the UPS ran out | n/a | 15/28 | 10/12 | 15/28 | 10/12 | 15/28 |
| Correct diagnosis before the UPS ran out | n/a | 12/28 | 10/12 | 15/28 | 10/12 | 15/28 |
| Readings, total (per case) | 159 (13.2) | 407 (14.5) | 46 (3.8) | 72 (2.6) | 43 (3.6) | 75 (2.7) |
| Approvals asked | 12 | 12 | 8 | 7 | 8 | 5 |
| Strong approvals asked (all denied by the batch rule) | 9 | 46 | 1 | 13 | 1 | 13 |
| Cost, actual | $1.135 | $3.377 | $0.112 | $0.164 | $0 | $0 |
| Cost, without the cached-input discount | $1.980 | $5.834 | n/a | $0.164 | $0 | $0 |
| Wall time per case, mean | 78 s | 87 s | n/a | 17 s | 1 s | 2 s |

**How to read these numbers:**
- **"Any diagnosis before the UPS ran out"** counts confident diagnoses made while the critical load was still powered
  or on UPS, right or wrong (the agent's 15 include its 3 confidently wrong ones); "correct diagnosis" counts only the
  right ones. "Insufficient information" never counts.
- **"Part-level correct" and "Insufficient information" overlap:** the 3 latent cases answered with insufficient
  information are correct by the latent rule and appear in both rows.
- **Explanation check:** for Hybrid v2 holdout, 15 model texts passed on the diagnosed cases and 13 templates were used
  for insufficient information (D41 rule). The check tests specific rules (the part named by kind, root cause before
  damaged parts, and since D47 the isolation sentence and safety wording); it is not an expert review of the text.
- **Hybrid v2 dev:** the D42 run on the same frozen configuration. Readings, approvals and UPS come from a replay
  without model calls whose tool logs and diagnoses were shown identical. Its wall time and token split were not kept.
- **Agent dev:** recorded before the load-lost fields existed (see the recording note).

### Holdout split: 25 visible faults and 3 latent faults

| | Agent | Hybrid v2 | Baseline |
|---|---|---|---|
| Visible: part-level correct | 14/25 | 15/25 | 15/25 |
| Visible: confidently wrong | 3/25 | 0/25 | 0/25 |
| Visible: insufficient information | 8/25 | 10/25 | 10/25 |
| Visible: UPS left at diagnosis, median | 4:30 | 8:30 | 8:00 |
| Visible: diagnosed before the UPS ran out | 15/25 | 15/25 | 15/25 |
| Visible: readings per case | 13.7 | 2.0 | 2.2 |
| Latent: correct (insufficient information) | 3/3 | 3/3 | 3/3 |
| Latent: readings per case | 21.7 | 7.0 | 7.0 |
| Latent: wall time per case | 231 s | 94 s | 12 s |

## Findings

1. **Hybrid v2 matched its ceiling on unseen faults.** It got the same 18 of 28 as the baseline on the true netlist,
   case by case. This is the planner working on our transcription of the drawing (with the repairs saved in that
   transcription), with no confident error. Its readings per case fell from 3.8 on dev to 2.6 on the holdout.
2. **The agent was confidently wrong 3 times on the holdout (0 on dev).**
   - h06 (controller input J14 open): it named harness wire W10.
   - h10 (wire W13 open): it named TS 17-18 stuck closed.
   - h25 (the other side of the burnout chain): it named the burnt coil, the consequence, not the misadjusted cut-off.
     On the dev chain (a7) the Chat agent found the root cause; the Responses transport had stopped at the coil in
     both its dev runs (D38). So the agent does not find the root cause reliably; the hybrid and the baseline did.
3. **8 visible faults ended in insufficient information for all three diagnosticians.** All are position-feedback
   faults (the 14A/14B circuits: TS 17-18, TS 17-16, wires 10, 13, 14, plug and jack pins 10, 13, 14, controller
   inputs J13, J14).
   - In these cases the switch transfers and the load is powered. The policy requires strong approval to isolate both
     sources while the load is powered, and the batch rule denies it. Without isolation there are no resistance
     readings to separate the candidates, so the right answer under this policy is to name the candidate set.
   - The hybrid does that: the template lists every part still possible. Twice the agent guessed instead (findings 2,
     h06 and h10).
   - This is the policy working as designed, not a reading failure, but it means a position fault cannot be pinned
     down without a planned outage.
   - h03, h08 and h10 are in the candidate set of the dev case x1. They are not observational twins of it (some
     reading separates them), so the exclusion rule kept them.
4. **UPS.**
   - The agent made 2 correct diagnoses after the UPS had run out (h13 TS 19-21 stuck open, 27 readings; h18 TS 5-22
     stuck open, 34 readings): diagnosis correct, critical load lost.
   - 4 more of its correct diagnoses came with 1 minute or less left (h05, h12, h21, h23).
   - The hybrid and the baseline never lost the load. Their median UPS left at diagnosis on visible faults was 8:30 and
     8:00, against the agent's 4:30.
5. **Cost.**
   - The agent cost $3.38 actual ($5.83 without the cached-input discount) for 28 cases, about $0.12 per case. It
     spent most on latent faults: $0.26 and 231 s per case to reach "insufficient information".
   - Hybrid v2 cost $0.164 in total, $0.006 per case (explanation calls only: no reading contradicted the transcription, so no repair ran). The baseline is free.
6. **Strong approvals.** The agent asked for strong approval 46 times (all denied), the hybrid 13. Every request was
   handled by the policy in code: the batch rule denied it, the run went on, no unsafe action executed.

## Disclosure

- The Hybrid v2 pipeline (drawing crops, reading conventions, the fault-free sequence checks, the repair messages,
  and the explanation step with its check, tuned in three versions for D41 and two for D42) was developed on this one
  drawing, on the 12 dev cases, after seeing the errors of the reads. Generalization to other drawings is not shown.
- The baseline uses the true netlist and is a ceiling for the planner, not an independent method.
- The fault catalog, the bench and the holdout sampler are written by the same author. Independence rests on seeded
  catalog sampling after the freeze, not on an outside test set.
- The ATS model, the assumptions and the troubleshooting sheet have not been reviewed by an electrical engineer.
- One run per diagnostician, 28 cases: small samples; differences of one or two cases are not significant.

## Recording note: UPS and critical load fields

The dev runs (agent, Hybrid v2 and info-gain baseline on the 12 dev cases, and the explanation checks of D41 and D42)
were recorded before the bench recorded when the UPS runs out (2026-10-31). In those runs:

- the bench drained the UPS but did not record the depletion time or mark the critical load as lost;
- the agent's panel view had no `load_lost` field and no depletion time in its `ups` block;
- the agent dev row has no "UPS left at diagnosis".

From that change on, every ATS trace carries `ups_at_diagnosis`, and the tables show it. Hybrid v2 and the baseline do
not read the new fields (the planner groups panel observations by `ups.draining` only); their tool logs and diagnoses
were checked identical offline after the change, so their dev UPS values above come from the replay. The agent does
see the new fields, so its dev numbers are not re-run results under the new panel; its holdout numbers are.

UPS autonomy (10 minutes) is a simulation parameter within the published data center range (source S7 in
docs/ATS_MODEL.md, assumption 14).

## Faults seen in the UI before the holdout

- 10:38, UI agent run on a random fault: TS:4-20 stuck_open (diagnosed correctly). Excluded from the holdout pool.
- 11:33, UI agent run on a random fault: **the fault was not recorded and is not remembered**. It may be in the holdout
  pool. Nothing was tuned on it: no code, prompt or setting changed because of that run.
- Free UI runs (Engineer mode, hybrid on dev cases) were not logged before 2026-10-31 noon; the paid runs are all in the
  spend ledger and used dev cases apart from the two above. From then on every UI run is written to the local list
  `runs/ui_runs.jsonl` (decision D44), and the holdout excluded every ATS fault in it (none were listed when it was
  made).
