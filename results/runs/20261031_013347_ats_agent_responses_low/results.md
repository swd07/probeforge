# ATS agent, muse-spark-1.3, effort low, transport responses (dev cases, not holdout)

| Case | Expected | Diagnosis | Conf. | Part correct | Confidently wrong | Meas. | Blocked | Approval / strong requests (denied) | UPS used s | Tokens | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_coil_open | TS:A-B open | TS:A-B burnt | 0.9 | no | no | 6 | 0 | 2 / 0 (0) | 210.0 | 98565 | $0.043 |
| a2_wire2_open | H1:W2_TSA-W2_P2 open | H1:W2_TSA-W2_P2 open | 0.98 | yes | no | 13 | 0 | 1 / 0 (0) | 420.0 | 100501 | $0.043 |
| a3_er_output | ER:J1-X1 stuck_open | insufficient_information | 0.0 | no | no | 13 | 0 | 2 / 3 (3) | 420.0 | 243600 | $0.090 |
| a4_cutoff_8_9 | TS:8-9 stuck_open | TS:8-9 stuck_open | 0.95 | yes | no | 6 | 0 | 0 / 1 (1) | 210.0 | 79421 | $0.043 |
| a5_jammed | TS jammed | TS jammed | 0.9 | yes | no | 7 | 0 | 2 / 0 (0) | 210.0 | 86368 | $0.040 |
| a6_pin1_open | XP:P1-J1 open | XP:P1-J1 open | 0.9 | yes | no | 10 | 0 | 2 / 2 (2) | 270.0 | 126816 | $0.062 |
| a7_burnout_chain | TS:8-9 stuck_closed or TS:71-72 stuck_closed | TS:A-B burnt | 0.9 | no (consequence, not cause) | yes | 13 | 0 | 3 / 0 (0) | 330.0 | 131304 | $0.082 |
| b1_wire7_open | H1:W7_TS4-W7_P7 open | H1:W7_TS4-W7_P7 open | 0.95 | yes | no | 6 | 0 | 0 / 0 (0) | 180.0 | 43268 | $0.028 |
| b2_pin18_open | XP:P18-J18 open | XP:P18-J18 open | 0.95 | yes | no | 8 | 0 | 0 / 0 (0) | 240.0 | 63488 | $0.042 |
| b3_wire6_open | H1:W6_TS5-W6_P6 open | H1:W6_TS5-W6_P6 open | 0.97 | yes | no | 6 | 0 | 0 / 0 (0) | 180.0 | 40318 | $0.032 |
| x1_aux14b_open | TS:17-16 stuck_open | insufficient_information | 0.35 | no | no | 14 | 0 | 0 / 2 (2) | 0.0 | 111255 | $0.055 |
| x2_engine_start_open | H1:W9A_TB15-W9A_P9 open | H1:W9A_TB15-W9A_P9 open | 0.98 | yes | no | 6 | 0 | 1 / 0 (0) | 330.0 | 75596 | $0.045 |

Correct at part level: 8/12; confidently wrong: 1; total cost $0.604.

Readings 108 (redundant 0), protocol errors 0, reasoning tokens 51777, cache hit rate 90.3%, cost $0.604 (uncached $1.723), mean wall time 38 s per case, errors 0.

Wall time 175 s.
