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

## Assumptions

In the netlist (S0):

1. TS solenoid A-B resistance 30 ohm (coil behind the rectifier): not documented, placeholder.
2. Utility and generator are ideal 120/208 V three-phase sources.
3. The generator starts while TB/TS 14-15 is closed (Feature 7); Feature 8 is not used by the modelled generator.
4. Controller inputs are ideal voltage and continuity sensing points; the controller's internal circuits are not modelled.
5. SE, ER and NR are modelled as contacts; their coils are inside the controller and driven by the controller logic.
6. The optional extension harness 309320-005 (Px/Jx) is not modelled: plug P mates directly with jack J.

In the bench simulator (S1, `src/probeforge/ats/bench.py`, the `ASSUMPTIONS` table), to be confirmed by the
electrical engineer:

7. **Transfer Failure**: declared if the position contacts do not confirm the other position 6 s after the command
   while the switch never left its origin (its position contact is still closed). The guide lists the event but its
   HELP section is missing.
8. **Position Error**: declared if the switch left its origin but the other position is never confirmed 6 s after the
   command, or if 14A / 14B disagree with a settled switch for 2 s. Same gap in the guide.
9. After either alarm the controller keeps SE / ER as commanded and does not retry by itself.
10. Generator start curve: 2 s cranking, rated voltage 10 s after the start signal, linear in between (the guide:
    "usually about 10 seconds"); Emergency is accepted at 90 % pickup, about 9.2 s after the start signal.
11. Mechanism: 0.15 s travel (open transition), top dead center at half travel; the coil operates above 70 % of
    nominal voltage across A-B; one operation per energization (a coil that stays energized holds the plunger, it does
    not drive the mechanism back); released before top dead center the mechanism falls back.
12. Coil burnout chain (replaces the fuse scenario, which 978741 does not support: there is no fuse in the TS operator
    circuit): if the cut-off contacts 8-9 and 71-72 do not open at top dead center, the coil stays energized with ER
    on and burns open after 30 s of continuous energization; a replacement coil burns again on the next transfer until
    the cut-off is fixed. A jammed mechanism also leaves the coil energized and burns it.
13. With both sources isolated the controller's relays drop out, and the switch can be operated manually for a check
    (a maintenance operation; sheet 3 only says a test and adjustment procedure sets the cut-off contacts): a jammed
    mechanism does not move, a cut-off contact that does not open still reads closed at the far position.
14. UPS autonomy 10 minutes and 30 s of virtual time per reading or action: simulation parameters, not ASCO data.
15. Frequency is not simulated: a source with voltage is at nominal frequency.

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
