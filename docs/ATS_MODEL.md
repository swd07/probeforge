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

Planned for the bench (S1), to be confirmed by the electrical engineer:

7. When the controller declares **Transfer Failure** (how long ER stays energized without the position contacts changing)
   and what it does afterwards. The guide lists the event but its HELP section is missing.
8. When the controller declares **Position Error** (which 14A / 14B combination). Same gap in the guide.
9. Generator start curve: crank and run-up to pickup in about 10 s (the guide: "usually about 10 seconds").
10. Mechanism travel time and the point where the cut-off contacts open.
11. Coil burnout chain (replaces the fuse scenario, which 978741 does not support: there is no fuse in the TS operator
    circuit): a cut-off contact that does not open at top dead center keeps the coil energized, the coil burns out, and
    a replacement coil burns out again on the next transfer until the cut-off contact is fixed.
12. UPS autonomy 10 minutes and 30 s of virtual time per reading or action: simulation parameters, not ASCO data.

## Documented but not modelled

Customer auxiliary contacts 14A (12-13, 31-32) and 14B (10-11, 29-30), option relay OP1, external Features 17 and 6B,
relay expansion modules 18RX / 18RX1, load current metering 23GB, RS-485 communications, strip heater (44G): not wired
on this unit or not relevant to the diagnosis.
