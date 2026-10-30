# Electrical engineer's review points and how the ATS bench covers them

The points below come from the electrical engineer's review of the motor-starter demo. Each is mapped to the ASCO
Series 300 Group G bench (see docs/ATS_MODEL.md for what is documented and what is assumed). Status is updated stage by
stage; nothing here claims that the engineer has reviewed the ATS model yet.

| # | Review point | How the ATS bench covers it | Stage | Status |
|---|---|---|---|---|
| 1 | A real schematic of real equipment, not an invented circuit | Netlist built only from ASCO drawing 978741 and outline 1522770-003; every part and net carries its source; a test checks it against the sheet 6 wire list and the sheet 2, 3, 4 paths | S0 | done |
| 2 | Only 1 or 2 scenarios, but fully realistic and working end to end | Main pair with the same first symptom (generator running, load not transferred, UPS draining): A operator circuit failure (ER commanded, TS does not operate), B emergency sensing circuit open (generator not accepted, no transfer command). Position feedback failure as an extra dev case | S1 to S5 | planned |
| 3 | Protection devices with real parameters | 52U service entrance breaker modelled with its documented type (Square D HL/JL, 175 to 225 A frames, thermal-magnetic). 978741 shows no fuse in the TS operator circuit, so the fuse scenario does not apply and is replaced by the cut-off contact to coil burnout chain (point 4) | S0, S1 | 52U in the netlist |
| 4 | Root cause, not consequence (a new fuse blows again; a jammed mechanism does not move on a repeat command) | Cut-off contacts that do not open at top dead center keep the coil energized; the coil burns open; a replacement coil burns again on the next transfer until the cut-off is fixed. A jammed mechanism leaves the coil energized and burns it. An isolated manual operation check finds the root cause once the coil has burnt. Labelled as assumptions for the engineer to confirm | S1 | done in the simulator |
| 5 | A repeat attempt or a second replacement after a repeat failure needs stronger approval | Policy in code with four tiers: allowed / approval (replace coil, repair wire or connector, replace or adjust a cut-off contact, replace controller) / strong approval (repeat transfer attempt after a failure, second replacement after a repeat failure) / never (manual handle operation under load, bypassing interlocks, paralleling sources) | S2 | done in code (S2) |
| 6 | Engineer mode: measure while holding a button or during a command | Reading during a transfer command (for example across the TS solenoid A-B while ER is energized), as an Engineer mode control and an agent tool; A = B blocked; reliable terminal clicks | S4 | done (S4) |
| 7 | Show suspected components and the next measurement on the schematic | Highlights on the redrawn diagram (the SVG has a hook on every part, terminal and net) | S4 | done (S4): the leading hypotheses are outlined on the drawing; the latest readings are labelled at their terminals |
| 8 | A troubleshooting sheet: symptom, possible causes, checks in a safe order, the separating measurement, expected readings per cause | Generated from the simulator for each scenario, then reviewed by the engineer | S6 (P1) | planned |
| 9 | A table of agent action limits | Generated from the ATS policy code (`RULES` in src/probeforge/ats/policy.py) into docs/ATS_MODEL.md, checked by a test; UI in S4 | S2, S4 | done: docs (S2) and UI (S4) |
| 10 | Compare agent and engineer decisions on the same faults | Engineer traces recorded in Engineer mode on the ATS bench, then Compare | S4 | planned |
| 11 | Fault indicators on the equipment as inputs | The Group G lights, display messages, alarms, event log and metering screen (documented in the User's Guide) are simulated; they are the first observation of every run | S1, S2 | simulated (S1) |

## Questions for the engineer (assumptions to confirm)

Research on public manufacturer sources (2026-10-31, docs/ATS_MODEL.md, sources S1 to S6) answers some of them; the
others stay open.

1. When does the Group G controller declare Transfer Failure, and what does it do afterwards? **Open** (exact timing;
   the guide lists the event without criteria).
2. Which position-contact combination gives Position Error? **Partly answered**: S2 documents Position Error at
   power-up when the controller sees source voltage before the position inputs, cleared by a full power cycle. The
   criteria during operation stay open.
3. Is the coil burnout chain realistic for this solenoid mechanism? **Answered (risk)**: S4 (ASCO patent) says bad
   cut-off timing may lead to coil overheating and switch failure. The burnout time stays open.
4. Realistic TS solenoid resistance and what a meter shows across A-B with the rectifier in circuit. **Open**: S6 has
   the table by frame, the D-frame value depends on the coil kit; through the bridge rectifier a meter reads diode
   junctions (bench limit documented).
5. Generator start-up time to acceptance, and mechanism travel time. **Answered**: guide (Emergency usually accepted
   about 10 s after NR drops), S1 and S3 (engine runs within 15 s in the transfer test), S5 (load transfer under
   100 ms; the bench now uses 0.08 s travel).
6. Does the controller keep ER energized after a Transfer Failure, and does it retry by itself? **Open** (retry
   behaviour): no source confirms an automatic retry.
7. Is a manual operation with both sources isolated a normal check, and how is the cut-off checked in the field?
   **Answered** for the manual operation: S1 and S3 (both sources disconnected and proven dead, the mechanism must move
   smoothly). The cut-off check follows the transfer switch test and adjustment procedure (978741 sheet 3).
8. How is a transfer repeated after a Transfer Failure, and does the controller restart its sequence when powered up
   again? **Partly answered**: the documented controlled repeat is the Transfer Test (S1, S3); a power cycle clears a
   power-up Position Error (S2). Restart after a Transfer Failure stays open.
