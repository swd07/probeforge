# [dev] Agent, frozen prompt, s01-s08 x3 (raw table)

Run 20261027_222844_agent_scenarios_low.

**agent on scenarios (muse-spark-1.3, effort low, approvals denied), 24 runs**

- Correct: 22/24
- Component right: 24/24 visible; failure mode right: 22/24; exact incl. part: 22/24
- Measurements: 200 total, 8.3 per case; redundant 24
- Evidence items: 47 functional_test, 72 instrument_reading
- Policy blocks: 2, protocol errors: 2, tool calls recovered from text: 0, missing hypothesis updates: 52, approval requests: 0 (denied 0), errors: 0
- Tokens: 1670773, cost $1.282 ($0.053 per case)
- Time: 913 s summed over cases, 176 s wall clock

| Case | Expected | Diagnosis | Correct | Component | Mode | Part | Meas | Redundant | Evidence F/I | Blocks | Turns | Tokens | Cost $ | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s01_r1 | FU1:1-2 open | FU1:1-2 open | yes | yes | yes | yes | 4 | 0 | 2/2 | 0 | 5 | 28593 | 0.036 | 14.4 |
| s02_r1 | SB1:11-12 stuck_open | SB1:11-12 stuck_open | yes | yes | yes | yes | 16 | 3 | 2/3 | 0 | 13 | 88859 | 0.052 | 38.9 |
| s03_r1 | KK1 tripped | KK1 tripped | yes | yes | yes | yes | 14 | 9 | 2/3 | 0 | 11 | 83319 | 0.079 | 43.4 |
| s04_r1 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 6 | 0 | 2/2 | 0 | 8 | 50565 | 0.044 | 31.2 |
| s05_r1 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 3 | 0 | 3/1 | 0 | 8 | 53848 | 0.066 | 51.5 |
| s06_r1 | KT:A1-A2 open | KT stuck | no | yes | no | no | 12 | 1 | 3/4 | 0 | 13 | 98699 | 0.098 | 74.3 |
| s07_r1 | KM3 welded | KM3 welded | yes | yes | yes | yes | 12 | 1 | 2/6 | 0 | 10 | 71058 | 0.065 | 35.9 |
| s08_r1 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 13 | 2 | 2/3 | 0 | 15 | 112283 | 0.081 | 59.0 |
| s01_r2 | FU1:1-2 open | FU1:1-2 open | yes | yes | yes | yes | 5 | 0 | 1/3 | 0 | 8 | 46956 | 0.046 | 14.5 |
| s02_r2 | SB1:11-12 stuck_open | SB1:11-12 stuck_open | yes | yes | yes | yes | 7 | 0 | 2/2 | 1 | 10 | 64111 | 0.037 | 25.3 |
| s03_r2 | KK1 tripped | KK1 tripped | yes | yes | yes | yes | 6 | 0 | 1/3 | 0 | 6 | 37059 | 0.038 | 18.2 |
| s04_r2 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 8 | 1 | 2/3 | 0 | 9 | 57594 | 0.033 | 24.9 |
| s05_r2 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 7 | 0 | 3/2 | 0 | 13 | 95324 | 0.071 | 57.3 |
| s06_r2 | KT:A1-A2 open | KT:A1-A2 open | yes | yes | yes | yes | 15 | 6 | 2/5 | 0 | 13 | 95254 | 0.076 | 67.2 |
| s07_r2 | KM3 welded | KM3 welded | yes | yes | yes | yes | 8 | 0 | 1/4 | 0 | 9 | 57784 | 0.042 | 35.6 |
| s08_r2 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 8 | 0 | 1/3 | 0 | 11 | 74638 | 0.044 | 28.4 |
| s01_r3 | FU1:1-2 open | FU1:1-2 open | yes | yes | yes | yes | 5 | 0 | 2/3 | 0 | 6 | 35004 | 0.018 | 13.4 |
| s02_r3 | SB1:11-12 stuck_open | SB1:11-12 stuck_open | yes | yes | yes | yes | 10 | 0 | 2/5 | 1 | 12 | 86805 | 0.054 | 33.1 |
| s03_r3 | KK1 tripped | KK1 tripped | yes | yes | yes | yes | 3 | 0 | 2/2 | 0 | 4 | 23409 | 0.014 | 10.6 |
| s04_r3 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 4 | 0 | 2/2 | 0 | 12 | 80461 | 0.048 | 31.5 |
| s05_r3 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 2 | 0 | 3/1 | 0 | 7 | 45575 | 0.038 | 37.6 |
| s06_r3 | KT:A1-A2 open | KT stuck | no | yes | no | no | 6 | 0 | 1/3 | 0 | 7 | 43910 | 0.032 | 29.2 |
| s07_r3 | KM3 welded | KM3 welded | yes | yes | yes | yes | 12 | 1 | 2/4 | 0 | 10 | 67512 | 0.052 | 46.2 |
| s08_r3 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 14 | 0 | 2/3 | 0 | 21 | 172153 | 0.117 | 91.0 |
