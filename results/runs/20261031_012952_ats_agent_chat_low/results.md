# ATS agent, muse-spark-1.3, effort low, transport chat (dev cases, not holdout)

| Case | Expected | Diagnosis | Conf. | Part correct | Confidently wrong | Meas. | Blocked | Approval / strong requests (denied) | UPS used s | Tokens | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_coil_open | TS:A-B open | TS:A-B open | 0.9 | yes | no | 10 | 1 | 2 / 0 (0) | 300.0 | 92171 | $0.060 |
| a2_wire2_open | H1:W2_TSA-W2_P2 open | H1:W2_TSA-W2_P2 open | 0.95 | yes | no | 12 | 1 | 2 / 2 (2) | 420.0 | 141009 | $0.130 |
| a3_er_output | ER:J1-X1 stuck_open | insufficient_information | 0.5 | no | no | 17 | 0 | 0 / 0 (0) | 540.0 | 85615 | $0.112 |
| a4_cutoff_8_9 | TS:8-9 stuck_open | TS:8-9 stuck_open | 0.95 | yes | no | 5 | 0 | 1 / 1 (1) | 210.0 | 65715 | $0.069 |
| a5_jammed | TS jammed | TS jammed | 0.9 | yes | no | 12 | 0 | 2 / 0 (0) | 360.0 | 86476 | $0.089 |
| a6_pin1_open | XP:P1-J1 open | XP:P1-J1 open | 0.95 | yes | no | 16 | 0 | 0 / 0 (0) | 510.0 | 75344 | $0.109 |
| a7_burnout_chain | TS:8-9 stuck_closed or TS:71-72 stuck_closed | TS:8-9 stuck_closed | 0.85 | yes | no | 12 | 0 | 3 / 0 (0) | 330.0 | 85938 | $0.093 |
| b1_wire7_open | H1:W7_TS4-W7_P7 open | H1:W7_TS4-W7_P7 open | 0.95 | yes | no | 9 | 1 | 0 / 0 (0) | 270.0 | 61735 | $0.072 |
| b2_pin18_open | XP:P18-J18 open | XP:P18-J18 open | 0.99 | yes | no | 21 | 0 | 1 / 0 (0) | 540.0 | 132402 | $0.103 |
| b3_wire6_open | H1:W6_TS5-W6_P6 open | H1:W6_TS5-W6_P6 open | 0.95 | yes | no | 22 | 0 | 0 / 0 (0) | 540.0 | 121141 | $0.110 |
| x1_aux14b_open | TS:17-16 stuck_open | insufficient_information | 0.4 | no | no | 18 | 0 | 0 / 6 (6) | 0.0 | 181270 | $0.119 |
| x2_engine_start_open | H1:W9A_TB15-W9A_P9 open | H1:W9A_TB15-W9A_P9 open | 0.95 | yes | no | 5 | 0 | 1 / 0 (0) | 210.0 | 82224 | $0.069 |

Correct at part level: 10/12; confidently wrong: 0; total cost $1.135.

Readings 159 (redundant 0), protocol errors 0, reasoning tokens 128004, cache hit rate 72.8%, cost $1.135 (uncached $1.980), mean wall time 78 s per case, errors 0.

Wall time 235 s.
