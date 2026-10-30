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
| 5 | A repeat attempt or a second replacement after a repeat failure needs stronger approval | Policy in code with four tiers: allowed / approval (replace coil, repair wire or connector, replace or adjust a cut-off contact, replace controller) / strong approval (repeat transfer attempt after a failure, second replacement after a repeat failure) / never (manual handle operation under load, bypassing interlocks, paralleling sources) | S2 | planned |
| 6 | Engineer mode: measure while holding a button or during a command | Reading during a transfer command (for example across the TS solenoid A-B while ER is energized), as an Engineer mode control and an agent tool; A = B blocked; reliable terminal clicks | S4 | planned |
| 7 | Show suspected components and the next measurement on the schematic | Highlights on the redrawn diagram (the SVG has a hook on every part, terminal and net) | S4 | hooks done (S0) |
| 8 | A troubleshooting sheet: symptom, possible causes, checks in a safe order, the separating measurement, expected readings per cause | Generated from the simulator for each scenario, then reviewed by the engineer | S6 (P1) | planned |
| 9 | A table of agent action limits | Generated from the ATS policy code, shown in the docs and the UI | S2, S4 | planned |
| 10 | Compare agent and engineer decisions on the same faults | Engineer traces recorded in Engineer mode on the ATS bench, then Compare | S4 | planned |
| 11 | Fault indicators on the equipment as inputs | The Group G lights, display messages, alarms, event log and metering screen (documented in the User's Guide) are simulated; they are the first observation of every run | S1, S2 | simulated (S1) |

## Questions for the engineer (assumptions to confirm)

1. When does the Group G controller declare Transfer Failure, and what does it do afterwards? (The guide lists the event,
   but its HELP section is missing.)
2. Which position-contact combination gives Position Error?
3. Is the coil burnout chain (cut-off contact not opening at top dead center) realistic for this solenoid mechanism?
4. Realistic TS solenoid resistance and what a meter shows across terminals A-B with the rectifier in circuit.
5. Generator start-up time to acceptance, and mechanism travel time.
6. Does the controller keep ER energized after a Transfer Failure (so a jammed mechanism burns the coil), and does it
   retry by itself?
7. Is a manual operation of the switch with both sources isolated a normal check for a jammed mechanism or a cut-off
   contact that does not open, and how is the cut-off checked in the field?
