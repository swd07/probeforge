# ATS troubleshooting sheet (families A and B)

**Generated from the simulator (our redrawing of drawing 978741), not reviewed by an engineer.**

Source: `scripts/ats_troubleshooting.py`. Each sheet starts 60 s after the Normal source failed, switch on Normal, generator healthy. Causes are every catalog fault (and the documented compound fault of the coil burnout chain) that gives exactly this symptom on the simulator. Checks are in a safe order (live readings, then isolation, then resistances and the manual operation check), each chosen to split the remaining causes best; the table gives the expected reading for every cause. The simulator's assumptions and limits are in docs/ATS_MODEL.md.

## A. Family A: operator circuit failure: Emergency accepted, transfer commanded, the switch does not operate

### Symptom

- Lights on: Emergency accepted, Load on Normal, Alert; display: Transfer Failure; alarms: Transfer Failure
- Generator: running; load powered: no (on UPS)
- Metering Normal 0/0/0 V, Emergency 208/208/208 V
- Event log: N Source Not Accepted (N Under Voltage); Engine Start; E Source Accepted; Transfer Failure (Switch on Normal)

### Possible causes (21)

1. TS jammed
2. TS 8-9 stuck_open
3. TS 71-72 stuck_open
4. TS A-B open
5. TS A-B burnt
6. SE X1-J2 stuck_open
7. SE J5-X2 stuck_open
8. ER J1-X1 stuck_open
9. ER X2-J16 stuck_open
10. XP P1-J1 open
11. XP P2-J2 open
12. XP P5-J5 open
13. XP P16-J16 open
14. H1 W1_TS8-W1_P1 open
15. H1 W2_TSA-W2_P2 open
16. H1 W5_TSB-W5_P5 open
17. H1 W16_TS72-W16_P16 open
18. H1 W17_TS4-W17_TS9 open
19. H1 W21_TS5-W21_TS71 open
20. TS 8-9 stuck_closed + TS 71-72 stuck_closed + TS A-B burnt
21. TS 6-7 stuck_closed + TS 69-70 stuck_closed + TS A-B burnt

### Checks in safe order

1. **Voltage TS:A to TS:B** (allowed (live, sources on)). 208 V: TS jammed, TS A-B open, TS A-B burnt, TS 8-9 stuck_closed + TS 71-72 stuck_closed + TS A-B burnt, TS 6-7 stuck_closed + TS 69-70 stuck_closed + TS A-B burnt; 0 V: the other 16
2. **Voltage TS:8 to TS:9** (allowed (live, sources on)). 208 V: TS 8-9 stuck_open; 0 V: the other 15
3. **Voltage TS:71 to TS:72** (allowed (live, sources on)). 208 V: TS 71-72 stuck_open; 0 V: the other 14
4. **Voltage XP:P1 to XP:J1** (allowed (live, sources on)). 208 V: XP P1-J1 open; 0 V: the other 13
5. **Voltage XP:P2 to XP:J2** (allowed (live, sources on)). 208 V: XP P2-J2 open; 0 V: the other 12
6. **Voltage XP:P5 to XP:J5** (allowed (live, sources on)). 208 V: XP P5-J5 open; 0 V: the other 11
7. **Voltage XP:P16 to XP:J16** (allowed (live, sources on)). 208 V: XP P16-J16 open; 0 V: the other 10
8. **Voltage H1:W1_TS8 to H1:W1_P1** (allowed (live, sources on)). 208 V: H1 W1_TS8-W1_P1 open; 0 V: the other 9
9. **Voltage H1:W2_TSA to H1:W2_P2** (allowed (live, sources on)). 208 V: H1 W2_TSA-W2_P2 open; 0 V: the other 8
10. **Voltage H1:W5_TSB to H1:W5_P5** (allowed (live, sources on)). 208 V: H1 W5_TSB-W5_P5 open; 0 V: the other 7
11. **Voltage H1:W16_TS72 to H1:W16_P16** (allowed (live, sources on)). 208 V: H1 W16_TS72-W16_P16 open; 0 V: the other 6
12. **Voltage H1:W17_TS4 to H1:W17_TS9** (allowed (live, sources on)). 208 V: H1 W17_TS4-W17_TS9 open; 0 V: the other 5
13. **Voltage H1:W21_TS5 to H1:W21_TS71** (allowed (live, sources on)). 208 V: H1 W21_TS5-W21_TS71 open; 0 V: the other 4
14. **Isolate both sources (52U open, generator locked out)** (approval (strong approval if the load were powered))
15. **Manual operation check, then resistance TS:8 to TS:9** (allowed only with both sources isolated). does not move, reads 0 ohm: TS jammed; moves, reads 0 ohm: TS 8-9 stuck_closed + TS 71-72 stuck_closed + TS A-B burnt; moves, reads open: the other 3
16. **Resistance TS:6 to TS:7** (allowed only with both sources isolated). 0 ohm: TS 6-7 stuck_closed + TS 69-70 stuck_closed + TS A-B burnt; open: TS A-B open, TS A-B burnt

### Expected reading per cause

| Cause | 1. Voltage TS:A to TS:B | 2. Voltage TS:8 to TS:9 | 3. Voltage TS:71 to TS:72 | 4. Voltage XP:P1 to XP:J1 | 5. Voltage XP:P2 to XP:J2 | 6. Voltage XP:P5 to XP:J5 | 7. Voltage XP:P16 to XP:J16 | 8. Voltage H1:W1_TS8 to H1:W1_P1 | 9. Voltage H1:W2_TSA to H1:W2_P2 | 10. Voltage H1:W5_TSB to H1:W5_P5 | 11. Voltage H1:W16_TS72 to H1:W16_P16 | 12. Voltage H1:W17_TS4 to H1:W17_TS9 | 13. Voltage H1:W21_TS5 to H1:W21_TS71 | 15. Manual operation check, then resistance TS:8 to TS:9 | 16. Resistance TS:6 to TS:7 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TS jammed | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | does not move, reads 0 ohm | open |
| TS 8-9 stuck_open | 0 V | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| TS 71-72 stuck_open | 0 V | 0 V | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| TS A-B open | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| TS A-B burnt | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| SE X1-J2 stuck_open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| SE J5-X2 stuck_open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| ER J1-X1 stuck_open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| ER X2-J16 stuck_open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| XP P1-J1 open | 0 V | 0 V | 0 V | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| XP P2-J2 open | 0 V | 0 V | 0 V | 0 V | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| XP P5-J5 open | 0 V | 0 V | 0 V | 0 V | 0 V | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| XP P16-J16 open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| H1 W1_TS8-W1_P1 open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| H1 W2_TSA-W2_P2 open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 208 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | open |
| H1 W5_TSB-W5_P5 open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 208 V | 0 V | 0 V | 0 V | moves, reads open | open |
| H1 W16_TS72-W16_P16 open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 208 V | 0 V | 0 V | moves, reads open | open |
| H1 W17_TS4-W17_TS9 open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 208 V | 0 V | moves, reads open | open |
| H1 W21_TS5-W21_TS71 open | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 208 V | moves, reads open | open |
| TS 8-9 stuck_closed + TS 71-72 stuck_closed + TS A-B burnt | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads 0 ohm | open |
| TS 6-7 stuck_closed + TS 69-70 stuck_closed + TS A-B burnt | 208 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | 0 V | moves, reads open | 0 ohm |

No reading in the menu searched (voltages, resistances, the position indicator, the manual operation check; a repeat transfer needs strong approval and is not used) separates: TS A-B open, TS A-B burnt (the same part in both: the same repair); SE X1-J2 stuck_open, SE J5-X2 stuck_open, ER J1-X1 stuck_open, ER X2-J16 stuck_open (relay contacts inside the controller, between points that cannot be probed: the controller is the repair).

Dev cases with this symptom: a1_coil_open, a2_wire2_open, a3_er_output, a4_cutoff_8_9, a5_jammed, a6_pin1_open, a7_burnout_chain (all among the causes: yes).

## B1. Family B: generator running but not accepted: no transfer command

### Symptom

- Lights on: Load on Normal; display: Waiting for Emergency Acceptable; alarms: none
- Generator: running; load powered: no (on UPS)
- Metering Normal 0/0/0 V, Emergency 0/208/0 V
- Event log: N Source Not Accepted (N Under Voltage); Engine Start

### Possible causes (3)

1. CP J7 open
2. XP P7-J7 open
3. H1 W7_TS4-W7_P7 open

### Checks in safe order

1. **Voltage XP:P7 to NN** (allowed (live, sources on)). 0 V: H1 W7_TS4-W7_P7 open; 120.1 V: CP J7 open, XP P7-J7 open
2. **Voltage XP:J7 to NN** (allowed (live, sources on)). 120.1 V: CP J7 open; 0 V: XP P7-J7 open

### Expected reading per cause

| Cause | 1. Voltage XP:P7 to NN | 2. Voltage XP:J7 to NN |
|---|---|---|
| CP J7 open | 120.1 V | 120.1 V |
| XP P7-J7 open | 120.1 V | 0 V |
| H1 W7_TS4-W7_P7 open | 0 V | 0 V |

Dev cases with this symptom: b1_wire7_open (all among the causes: yes).

## B2. Family B: generator running but not accepted: no transfer command

### Symptom

- Lights on: Load on Normal; display: Waiting for Emergency Acceptable; alarms: none
- Generator: running; load powered: no (on UPS)
- Metering Normal 0/0/0 V, Emergency 0/0/208 V
- Event log: N Source Not Accepted (N Under Voltage); Engine Start

### Possible causes (3)

1. CP J18 open
2. XP P18-J18 open
3. H1 W25_TS19-W25_P18 open

### Checks in safe order

1. **Voltage XP:P18 to NN** (allowed (live, sources on)). 0 V: H1 W25_TS19-W25_P18 open; 120.1 V: CP J18 open, XP P18-J18 open
2. **Voltage XP:J18 to NN** (allowed (live, sources on)). 120.1 V: CP J18 open; 0 V: XP P18-J18 open

### Expected reading per cause

| Cause | 1. Voltage XP:P18 to NN | 2. Voltage XP:J18 to NN |
|---|---|---|
| CP J18 open | 120.1 V | 120.1 V |
| XP P18-J18 open | 120.1 V | 0 V |
| H1 W25_TS19-W25_P18 open | 0 V | 0 V |

Dev cases with this symptom: b2_pin18_open (all among the causes: yes).

## B3. Family B: generator running but not accepted: no transfer command

### Symptom

- Lights on: Load on Normal; display: Waiting for Emergency Acceptable; alarms: none
- Generator: running; load powered: no (on UPS)
- Metering Normal 0/0/0 V, Emergency 208/0/0 V
- Event log: N Source Not Accepted (N Under Voltage); Engine Start

### Possible causes (3)

1. CP J6 open
2. XP P6-J6 open
3. H1 W6_TS5-W6_P6 open

### Checks in safe order

1. **Voltage XP:P6 to NN** (allowed (live, sources on)). 0 V: H1 W6_TS5-W6_P6 open; 120.1 V: CP J6 open, XP P6-J6 open
2. **Voltage XP:J6 to NN** (allowed (live, sources on)). 120.1 V: CP J6 open; 0 V: XP P6-J6 open

### Expected reading per cause

| Cause | 1. Voltage XP:P6 to NN | 2. Voltage XP:J6 to NN |
|---|---|---|
| CP J6 open | 120.1 V | 120.1 V |
| XP P6-J6 open | 120.1 V | 0 V |
| H1 W6_TS5-W6_P6 open | 0 V | 0 V |

Dev cases with this symptom: b3_wire6_open (all among the causes: yes).
