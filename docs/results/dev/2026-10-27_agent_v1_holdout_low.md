# [dev] Agent v1 on holdout, muse-spark-1.3, effort low (2026-10-27)

Run 20261027_215747_agent_holdout_low. v1 = before the text tool-call recovery, turn-budget warnings and neutral framing.

**agent on holdout (muse-spark-1.3, effort low), 40 runs**

- Correct: 26/40 (visible 25/30, latent 1/10)
- Component right: 25/30 visible; failure mode right: 25/30; exact incl. part: 25/30
- Measurements: 328 total, 8.2 per case; redundant 14
- Evidence items: 55 functional_test, 79 instrument_reading
- Policy blocks: 0, protocol errors: 72, errors: 0
- Tokens: 5618269, cost $3.854 ($0.096 per case)
- Time: 3299 s summed over cases, 479 s wall clock

| Case | Expected | Diagnosis | Correct | Component | Mode | Part | Meas | Redundant | Evidence F/I | Blocks | Turns | Tokens | Cost $ | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| h01 | KM1:53-54 stuck_closed | KM1:53-54 stuck_closed | yes | yes | yes | yes | 4 | 0 | 2/2 | 0 | 10 | 65555 | 0.075 | 49.0 |
| h02 | KM4:1-2 stuck_open | KM4:1-2 stuck_open | yes | yes | yes | yes | 13 | 0 | 2/4 | 0 | 25 | 211847 | 0.119 | 93.7 |
| h03 | HL4:X1-X2 open | HL4:X1-X2 open | yes | yes | yes | yes | 4 | 0 | 2/3 | 0 | 15 | 93342 | 0.052 | 32.2 |
| h04 | KM1:43-44 stuck_open | KM1:43-44 stuck_open | yes | yes | yes | yes | 22 | 0 | 2/4 | 0 | 17 | 145250 | 0.086 | 61.3 |
| h05 | KM2:53-54 stuck_open | KM2:53-54 stuck_open | yes | yes | yes | yes | 3 | 0 | 2/2 | 0 | 15 | 95848 | 0.057 | 34.4 |
| h06 | SB1:11-12 stuck_closed | SB1:11-12 stuck_closed | yes | yes | yes | yes | 3 | 0 | 3/1 | 0 | 11 | 64617 | 0.044 | 32.7 |
| h07 | KM4:A1-A2 open | KM4:A1-A2 open | yes | yes | yes | yes | 6 | 1 | 3/3 | 0 | 19 | 145808 | 0.097 | 68.0 |
| h08 | KM4:A1-A2 short | KM4:A1-A2 short | yes | yes | yes | yes | 6 | 0 | 2/3 | 0 | 7 | 41940 | 0.038 | 35.9 |
| h09 | KM3:5-6 stuck_open | KM3:5-6 stuck_open | yes | yes | yes | yes | 12 | 0 | 2/3 | 0 | 19 | 142670 | 0.082 | 69.8 |
| h10 | KM2:13-14 stuck_closed | insufficient_information | no | no | no | no | 2 | 1 | 2/2 | 0 | 7 | 50282 | 0.086 | 85.8 |
| h11 | KT:55-56 stuck_open | KT:55-56 stuck_open | yes | yes | yes | yes | 4 | 0 | 2/1 | 0 | 16 | 106527 | 0.057 | 51.6 |
| h12 | KM3:21-22 stuck_open | KM3:21-22 stuck_open | yes | yes | yes | yes | 9 | 3 | 2/3 | 0 | 11 | 71465 | 0.045 | 34.8 |
| h13 | SB2:13-14 stuck_closed | insufficient_information | no | no | no | no | 1 | 0 | 2/1 | 0 | 7 | 48687 | 0.086 | 88.1 |
| h14 | KK1:3-4 open | KK1:3-4 open | yes | yes | yes | yes | 12 | 0 | 1/3 | 0 | 13 | 99187 | 0.064 | 38.6 |
| h15 | KM4:21-22 stuck_open | KM4:21-22 stuck_open | yes | yes | yes | yes | 6 | 0 | 2/2 | 0 | 12 | 74464 | 0.044 | 40.7 |
| h16 | KT:67-68 stuck_open | KT:67-68 stuck_open | yes | yes | yes | yes | 9 | 4 | 2/3 | 0 | 19 | 148823 | 0.084 | 55.2 |
| h17 | KK1:1-2 open | KK1:1-2 open | yes | yes | yes | yes | 6 | 0 | 1/3 | 0 | 12 | 82268 | 0.048 | 34.4 |
| h18 | KM3:A1-A2 open | KM3:A1-A2 open | yes | yes | yes | yes | 10 | 0 | 1/3 | 0 | 19 | 147842 | 0.086 | 72.0 |
| h19 | KT:A1-A2 short | KT:A1-A2 short | yes | yes | yes | yes | 5 | 0 | 1/2 | 0 | 11 | 69646 | 0.043 | 29.8 |
| h20 | KM4 welded | KM4 welded | yes | yes | yes | yes | 9 | 0 | 1/4 | 0 | 19 | 145083 | 0.093 | 77.0 |
| h21 | HL3:X1-X2 open | HL3:X1-X2 open | yes | yes | yes | yes | 7 | 0 | 2/2 | 0 | 13 | 86432 | 0.049 | 29.2 |
| h22 | M1:W1-W2 open | M1:W1-W2 open | yes | yes | yes | yes | 5 | 0 | 2/2 | 0 | 6 | 38678 | 0.031 | 27.7 |
| h23 | QF1:1-2 open | QF1:1-2 open | yes | yes | yes | yes | 8 | 0 | 1/4 | 0 | 10 | 62848 | 0.037 | 20.1 |
| h24 | SB3:13-14 stuck_open | SB3:13-14 stuck_open | yes | yes | yes | yes | 4 | 0 | 2/2 | 0 | 9 | 52768 | 0.027 | 21.8 |
| h25 | KM1 welded | insufficient_information | no | no | no | no | 2 | 1 | 2/2 | 0 | 7 | 48013 | 0.080 | 77.6 |
| h26 | KM1:1-2 stuck_open | insufficient_information | no | no | no | no | 8 | 1 | 2/4 | 0 | 14 | 102327 | 0.084 | 89.0 |
| h27 | KM2:A1-A2 open | KM2:A1-A2 open | yes | yes | yes | yes | 4 | 0 | 2/2 | 0 | 13 | 92479 | 0.051 | 31.8 |
| h28 | KM1:A1-A2 short | KM1:A1-A2 short | yes | yes | yes | yes | 9 | 0 | 1/3 | 0 | 11 | 84439 | 0.052 | 35.6 |
| h29 | KT stuck | KT stuck | yes | yes | yes | yes | 6 | 0 | 2/4 | 0 | 7 | 43836 | 0.037 | 35.3 |
| h30 | KM4:5-6 stuck_closed | no_diagnosis | no | no | no | no | 23 | 0 | 0/0 | 0 | 30 | 319599 | 0.217 | 202.8 |
| l01 (latent) | KK1:95-96 stuck_closed | no_diagnosis | no | no | no | no | 18 | 0 | 0/0 | 0 | 30 | 294058 | 0.262 | 313.8 |
| l02 (latent) | KM4:21-22 stuck_closed | no_diagnosis | no | no | no | no | 11 | 0 | 0/0 | 0 | 30 | 263161 | 0.137 | 109.3 |
| l03 (latent) | KM3:3-4 stuck_closed | no_diagnosis | no | no | no | no | 8 | 1 | 0/0 | 0 | 30 | 253713 | 0.137 | 114.6 |
| l04 (latent) | HL2:X1-X2 open | HL2:X1-X2 open | yes | yes | yes | yes | 3 | 0 | 2/2 | 0 | 24 | 184096 | 0.088 | 65.4 |
| l05 (latent) | KM2:21-22 stuck_closed | no_diagnosis | no | no | no | no | 11 | 0 | 0/0 | 0 | 30 | 269953 | 0.163 | 146.4 |
| l06 (latent) | KM2:3-4 stuck_closed | no_diagnosis | no | no | no | no | 15 | 0 | 0/0 | 0 | 30 | 277633 | 0.195 | 198.2 |
| l07 (latent) | KM3:1-2 stuck_closed | no_diagnosis | no | no | no | no | 5 | 0 | 0/0 | 0 | 30 | 270870 | 0.188 | 194.9 |
| l08 (latent) | KM2:43-44 stuck_closed | no_diagnosis | no | no | no | no | 8 | 0 | 0/0 | 0 | 30 | 273473 | 0.199 | 178.4 |
| l09 (latent) | KM1:21-22 stuck_closed | no_diagnosis | no | no | no | no | 12 | 0 | 0/0 | 0 | 30 | 268200 | 0.203 | 158.7 |
| l10 (latent) | KM3:5-6 stuck_closed | no_diagnosis | no | no | no | no | 15 | 2 | 0/0 | 0 | 30 | 280542 | 0.230 | 163.8 |
