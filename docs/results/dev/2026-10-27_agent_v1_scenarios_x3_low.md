# [dev] Agent v1 on s01-s08 x3, muse-spark-1.3, effort low (2026-10-27)

Run 20261027_215748_agent_scenarios_low. v1 = before the text tool-call recovery, turn-budget warnings and neutral framing.

**agent on scenarios (muse-spark-1.3, effort low), 24 runs**

- Correct: 19/24
- Component right: 22/24 visible; failure mode right: 19/24; exact incl. part: 18/24
- Measurements: 137 total, 5.7 per case; redundant 9
- Evidence items: 43 functional_test, 65 instrument_reading
- Policy blocks: 0, protocol errors: 28, errors: 0
- Tokens: 1922362, cost $1.212 ($0.050 per case)
- Time: 897 s summed over cases, 124 s wall clock

| Case | Expected | Diagnosis | Correct | Component | Mode | Part | Meas | Redundant | Evidence F/I | Blocks | Turns | Tokens | Cost $ | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s01_r1 | FU1:1-2 open | FU1:1-2 open | yes | yes | yes | yes | 5 | 0 | 2/3 | 0 | 10 | 60348 | 0.055 | 21.8 |
| s02_r1 | SB1:11-12 stuck_open | SB1:11-12 stuck_open | yes | yes | yes | yes | 8 | 0 | 2/4 | 0 | 12 | 83023 | 0.054 | 38.0 |
| s03_r1 | KK1 tripped | KK1 tripped | yes | yes | yes | yes | 3 | 0 | 2/3 | 0 | 4 | 24390 | 0.034 | 23.5 |
| s04_r1 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 4 | 0 | 2/2 | 0 | 10 | 60516 | 0.033 | 29.9 |
| s05_r1 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 2 | 0 | 2/1 | 0 | 8 | 53380 | 0.053 | 61.9 |
| s06_r1 | KT:A1-A2 open | KT stuck | no | yes | no | no | 9 | 2 | 2/5 | 0 | 10 | 72230 | 0.054 | 54.6 |
| s07_r1 | KM3 welded | KM3 welded | yes | yes | yes | yes | 6 | 0 | 2/2 | 0 | 10 | 63849 | 0.048 | 52.0 |
| s08_r1 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 5 | 0 | 2/3 | 0 | 9 | 55726 | 0.039 | 32.6 |
| s01_r2 | FU1:1-2 open | FU1:1-2 open | yes | yes | yes | yes | 4 | 0 | 1/3 | 0 | 6 | 33961 | 0.034 | 16.0 |
| s02_r2 | SB1:11-12 stuck_open | no_diagnosis | no | no | no | no | 11 | 3 | 0/0 | 0 | 30 | 303478 | 0.140 | 83.5 |
| s03_r2 | KK1 tripped | no_diagnosis | no | no | no | no | 11 | 0 | 0/0 | 0 | 30 | 285479 | 0.143 | 78.0 |
| s04_r2 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 4 | 0 | 2/4 | 0 | 8 | 52593 | 0.030 | 24.5 |
| s05_r2 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 0 | 0 | 3/0 | 0 | 6 | 42428 | 0.035 | 30.5 |
| s06_r2 | KT:A1-A2 open | KT stuck | no | yes | no | no | 6 | 1 | 2/3 | 0 | 9 | 56868 | 0.031 | 24.2 |
| s07_r2 | KM3 welded | KM3 welded | yes | yes | yes | yes | 9 | 1 | 2/4 | 0 | 15 | 112782 | 0.073 | 57.7 |
| s08_r2 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 5 | 0 | 2/3 | 0 | 9 | 56152 | 0.035 | 30.0 |
| s01_r3 | FU1:1-2 open | FU1 open | yes | yes | yes | no | 3 | 0 | 2/3 | 0 | 7 | 41653 | 0.031 | 18.5 |
| s02_r3 | SB1:11-12 stuck_open | SB1:11-12 stuck_open | yes | yes | yes | yes | 4 | 0 | 2/4 | 0 | 10 | 63874 | 0.034 | 26.2 |
| s03_r3 | KK1 tripped | KK1 tripped | yes | yes | yes | yes | 6 | 0 | 2/3 | 0 | 10 | 64370 | 0.042 | 28.1 |
| s04_r3 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 10 | 1 | 2/4 | 0 | 17 | 119332 | 0.055 | 37.0 |
| s05_r3 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 0 | 0 | 2/0 | 0 | 4 | 24856 | 0.021 | 24.2 |
| s06_r3 | KT:A1-A2 open | KT stuck | no | yes | no | no | 4 | 0 | 2/3 | 0 | 10 | 64237 | 0.046 | 39.6 |
| s07_r3 | KM3 welded | KM3 welded | yes | yes | yes | yes | 9 | 1 | 2/3 | 0 | 9 | 58428 | 0.042 | 35.2 |
| s08_r3 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 9 | 0 | 1/5 | 0 | 9 | 68409 | 0.048 | 29.8 |
