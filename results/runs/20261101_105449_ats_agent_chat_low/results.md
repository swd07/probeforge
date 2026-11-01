# ATS agent, muse-spark-1.3, effort low, transport chat (dev cases, not holdout)

| Case | Expected | Diagnosis | Conf. | Part correct | Confidently wrong | Meas. | Blocked | Approval / strong requests (denied) | UPS used s | UPS left at diagnosis | Tokens | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_coil_open | TS:A-B open | TS:A-B burnt | 0.95 | no | no | 11 | 0 | 3 / 0 (0) | 330.0 | 210 s | 93388 | $0.088 |
| a4_cutoff_8_9 | TS:8-9 stuck_open | TS:8-9 stuck_open | 0.95 | yes | no | 19 | 0 | 0 / 0 (0) | 540.0 | 0 s, load lost | 116781 | $0.145 |
| a7_burnout_chain | TS:8-9 stuck_closed or TS:71-72 stuck_closed | TS:A-B open | 0.9 | no | yes | 7 | 0 | 2 / 0 (0) | 300.0 | 240 s | 93676 | $0.094 |
| b1_wire7_open | H1:W7_TS4-W7_P7 open | H1:W7_TS4-W7_P7 open | 0.9 | yes | no | 24 | 0 | 0 / 0 (0) | 540.0 | 0 s, load lost | 113726 | $0.137 |
| x1_aux14b_open | TS:17-16 stuck_open | insufficient_information | 0.0 | no | no | 12 | 0 | 0 / 4 (4) | 0.0 | 588 s | 119574 | $0.135 |

Correct at part level: 2/5; confidently wrong: 1; diagnosed before the UPS ran out 2/5, UPS left at diagnosis median 210 s; total cost $0.598.

Readings 73 (redundant 0), protocol errors 0, reasoning tokens 61809, cache hit rate 57.3%, cost $0.598 (uncached $0.891), mean wall time 65 s per case, errors 0.

Wall time 82 s.
