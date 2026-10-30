# ATS bench dev scenarios (ASCO Series 300 Group G)

Dev cases for the ATS bench: hand-written, visible while the bench and the agent profile are built, so their results
are dev results. The held-out ATS faults are created only after the freeze (stage S5).

Every case starts with the switch on Normal, the Normal source lost at t = 0 (utility side, 52U stays closed) and the
generator healthy. `fault` is hidden from the agent; `symptom` is what the simulator shows 60 s after the outage and is
checked by tests/test_ats_bench.py.

- Family A, operator circuit failure: the emergency source is accepted, ER is commanded, the TS does not operate.
- Family B, generator running but not accepted: an emergency sensing circuit is open, no transfer command.
- Extras: position feedback failure (the switch transfers, the controller cannot confirm it), engine start circuit open.
