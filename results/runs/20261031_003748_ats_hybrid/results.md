# ATS Hybrid v2 (dev cases, not holdout)

Disclosure: the hybrid pipeline (drawing crops, reading conventions, the fault-free sequence checks and the repair messages) was developed on this one drawing, after seeing the errors of these reads. Generalization to other drawings is not shown.

| Case | Expected | Diagnosis | Correct | Confidently wrong | Meas. | Approval / strong (denied) | Cost |
|---|---|---|---|---|---|---|---|
| a1_coil_open | TS:A-B open | TS:A-B open | yes | no | 3 | 2 / 0 (0) | $0.005 |
| a4_cutoff_8_9 | TS:8-9 stuck_open | TS:8-9 stuck_open | yes | no | 2 | 0 / 0 (0) | $0.004 |
| a7_burnout_chain | TS:8-9 stuck_closed or TS:71-72 stuck_closed | TS:8-9 stuck_closed | yes | no | 2 | 2 / 0 (0) | $0.005 |
| b1_wire7_open | H1:W7_TS4-W7_P7 open | H1:W7_TS4-W7_P7 open | yes | no | 2 | 0 / 0 (0) | $0.006 |
| x2_engine_start_open | H1:W9A_TB15-W9A_P9 open | H1:W9A_TB15-W9A_P9 open | yes | no | 3 | 1 / 0 (0) | $0.006 |

Correct 5/5; confidently wrong 0; cost $0.026.
