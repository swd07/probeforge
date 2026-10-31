# ATS agent, muse-spark-1.3, effort low (dev cases, not holdout)

| Case | Expected | Diagnosis | Conf. | Part correct | Confidently wrong | Meas. | Blocked | Approval / strong requests (denied) | UPS used s | Tokens | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_coil_open | TS:A-B open | TS:A-B burnt | 0.95 | no | no | 7 | 0 | 3 / 0 (1) | 180.0 | 62148 | $0.077 |
| a4_cutoff_8_9 | TS:8-9 stuck_open | TS:8-9 stuck_open | 0.95 | yes | no | 9 | 0 | 0 / 0 (0) | 270.0 | 50640 | $0.079 |
| a7_burnout_chain | TS:8-9 stuck_closed or TS:71-72 stuck_closed | TS:8-9 stuck_closed | 0.75 | yes | no | 15 | 0 | 3 / 0 (0) | 360.0 | 82584 | $0.118 |
| b1_wire7_open | H1:W7_TS4-W7_P7 open | H1:W7_TS4-W7_P7 open | 0.99 | yes | no | 19 | 0 | 1 / 0 (0) | 540.0 | 113519 | $0.114 |
| x1_aux14b_open | TS:17-16 stuck_open | TS:17-16 stuck_open | 0.92 | yes | no | 24 | 0 | 2 / 1 (1) | 510.0 | 142566 | $0.130 |

Correct at part level: 4/5; confidently wrong: 0; total cost $0.517.

Wall time 100 s.
