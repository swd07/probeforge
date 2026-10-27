# [dev] Agent v2 on s01-s08 x3, muse-spark-1.3, effort low (2026-10-27)

Run 20261027_220754_agent_scenarios_low.

**agent on scenarios (muse-spark-1.3, effort low), 24 runs**

- Correct: 22/24
- Component right: 24/24 visible; failure mode right: 22/24; exact incl. part: 22/24
- Measurements: 144 total, 6.0 per case; redundant 9
- Evidence items: 44 functional_test, 68 instrument_reading
- Policy blocks: 1, protocol errors: 36, tool calls recovered from text: 0, errors: 0
- Tokens: 1980244, cost $1.312 ($0.055 per case)
- Time: 976 s summed over cases, 168 s wall clock

| Case | Expected | Diagnosis | Correct | Component | Mode | Part | Meas | Redundant | Evidence F/I | Blocks | Turns | Tokens | Cost $ | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s01_r1 | FU1:1-2 open | FU1:1-2 open | yes | yes | yes | yes | 4 | 0 | 2/4 | 0 | 7 | 45757 | 0.048 | 22.0 |
| s02_r1 | SB1:11-12 stuck_open | SB1:11-12 stuck_open | yes | yes | yes | yes | 7 | 0 | 2/3 | 0 | 10 | 65925 | 0.035 | 30.4 |
| s03_r1 | KK1 tripped | KK1 tripped | yes | yes | yes | yes | 3 | 0 | 1/3 | 0 | 6 | 35853 | 0.048 | 19.3 |
| s04_r1 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 8 | 1 | 2/3 | 0 | 12 | 78029 | 0.043 | 36.0 |
| s05_r1 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 3 | 0 | 2/2 | 0 | 8 | 53190 | 0.053 | 66.7 |
| s06_r1 | KT:A1-A2 open | KT stuck | no | yes | no | no | 6 | 1 | 2/3 | 0 | 14 | 91837 | 0.053 | 36.9 |
| s07_r1 | KM3 welded | KM3 welded | yes | yes | yes | yes | 8 | 0 | 2/4 | 0 | 20 | 155741 | 0.096 | 80.3 |
| s08_r1 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 3 | 0 | 1/2 | 0 | 8 | 54356 | 0.047 | 37.2 |
| s01_r2 | FU1:1-2 open | FU1:1-2 open | yes | yes | yes | yes | 4 | 0 | 1/3 | 0 | 7 | 39678 | 0.040 | 15.0 |
| s02_r2 | SB1:11-12 stuck_open | SB1:11-12 stuck_open | yes | yes | yes | yes | 6 | 0 | 2/2 | 1 | 9 | 54410 | 0.029 | 21.3 |
| s03_r2 | KK1 tripped | KK1 tripped | yes | yes | yes | yes | 8 | 0 | 2/2 | 0 | 12 | 82098 | 0.077 | 51.3 |
| s04_r2 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 7 | 1 | 2/2 | 0 | 14 | 92829 | 0.049 | 35.9 |
| s05_r2 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 1 | 0 | 2/1 | 0 | 9 | 60628 | 0.054 | 58.9 |
| s06_r2 | KT:A1-A2 open | KT:A1-A2 open | yes | yes | yes | yes | 8 | 0 | 2/4 | 0 | 15 | 100777 | 0.061 | 50.7 |
| s07_r2 | KM3 welded | KM3 welded | yes | yes | yes | yes | 9 | 0 | 2/4 | 0 | 15 | 107421 | 0.070 | 56.1 |
| s08_r2 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 12 | 3 | 1/3 | 0 | 21 | 160063 | 0.080 | 53.3 |
| s01_r3 | FU1:1-2 open | FU1:1-2 open | yes | yes | yes | yes | 6 | 1 | 2/3 | 0 | 7 | 41394 | 0.033 | 16.1 |
| s02_r3 | SB1:11-12 stuck_open | SB1:11-12 stuck_open | yes | yes | yes | yes | 11 | 0 | 2/4 | 0 | 18 | 133618 | 0.074 | 52.1 |
| s03_r3 | KK1 tripped | KK1 tripped | yes | yes | yes | yes | 3 | 0 | 2/3 | 0 | 4 | 23468 | 0.021 | 12.6 |
| s04_r3 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 4 | 1 | 2/2 | 0 | 9 | 54643 | 0.029 | 20.6 |
| s05_r3 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 0 | 0 | 3/0 | 0 | 7 | 43697 | 0.037 | 44.1 |
| s06_r3 | KT:A1-A2 open | KT stuck | no | yes | no | no | 9 | 1 | 2/4 | 0 | 13 | 85518 | 0.054 | 40.5 |
| s07_r3 | KM3 welded | KM3 welded | yes | yes | yes | yes | 7 | 0 | 1/4 | 0 | 22 | 199412 | 0.113 | 74.6 |
| s08_r3 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 7 | 0 | 2/3 | 0 | 17 | 119902 | 0.067 | 44.1 |
