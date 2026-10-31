# ATS bench results (ASCO Series 300 Group G, drawing 978741)

Status: the S5 holdout has not been run yet. This file will hold its results next to the dev reference numbers.

## Recording note: UPS and critical load fields

The dev runs (agent, Hybrid v2 and info-gain baseline on the 12 dev cases, and the explanation checks of D41 and D42)
were recorded before the bench recorded when the UPS runs out (2026-10-31). In those runs:

- the bench drained the UPS but did not record the depletion time or mark the critical load as lost;
- the agent's panel view had no `load_lost` field and no depletion time in its `ups` block;
- the results tables have no "UPS left at diagnosis" values: the generators print n/a for those rows.

From this change on, every ATS trace carries `ups_at_diagnosis` (UPS time left when the diagnosis was made, whether the
critical load was already lost, and when the UPS ran out), and the tables show it. Hybrid v2 and the baseline do not
read the new fields (the planner groups panel observations by `ups.draining` only); their tool logs and diagnoses were
checked identical offline after the change. The agent does see the new fields, so agent dev numbers are not re-run
results under the new panel.

UPS autonomy (10 minutes) is a simulation parameter within the published data center range (source S7 in
docs/ATS_MODEL.md, assumption 14).
