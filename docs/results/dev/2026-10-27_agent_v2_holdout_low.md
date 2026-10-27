# [dev] Agent v2 on holdout, muse-spark-1.3, effort low (2026-10-27)

Run 20261027_220753_agent_holdout_low.

**agent on holdout (muse-spark-1.3, effort low), 40 runs**

- Correct: 35/40 (visible 25/30, latent 10/10)
- Component right: 25/30 visible; failure mode right: 25/30; exact incl. part: 25/30
- Measurements: 277 total, 6.9 per case; redundant 8
- Evidence items: 91 functional_test, 110 instrument_reading
- Policy blocks: 2, protocol errors: 87, tool calls recovered from text: 4, errors: 0
- Tokens: 5663247, cost $3.680 ($0.092 per case)
- Time: 3100 s summed over cases, 428 s wall clock

| Case | Expected | Diagnosis | Correct | Component | Mode | Part | Meas | Redundant | Evidence F/I | Blocks | Turns | Tokens | Cost $ | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| h01 | KM1:53-54 stuck_closed | KM1:53-54 stuck_closed | yes | yes | yes | yes | 6 | 0 | 2/4 | 0 | 9 | 59024 | 0.066 | 39.8 |
| h02 | KM4:1-2 stuck_open | KM4:1-2 stuck_open | yes | yes | yes | yes | 12 | 1 | 1/3 | 0 | 24 | 195784 | 0.129 | 128.1 |
| h03 | HL4:X1-X2 open | HL4:X1-X2 open | yes | yes | yes | yes | 3 | 0 | 1/2 | 0 | 11 | 67041 | 0.037 | 24.1 |
| h04 | KM1:43-44 stuck_open | KM1:43-44 stuck_open | yes | yes | yes | yes | 10 | 3 | 2/4 | 0 | 17 | 136181 | 0.086 | 60.1 |
| h05 | KM2:53-54 stuck_open | KM2:53-54 stuck_open | yes | yes | yes | yes | 5 | 0 | 2/3 | 0 | 12 | 74011 | 0.056 | 37.5 |
| h06 | SB1:11-12 stuck_closed | SB1:11-12 stuck_closed | yes | yes | yes | yes | 2 | 0 | 1/2 | 0 | 7 | 41367 | 0.028 | 33.8 |
| h07 | KM4:A1-A2 open | KM4:A1-A2 open | yes | yes | yes | yes | 5 | 0 | 2/3 | 0 | 24 | 180906 | 0.097 | 72.0 |
| h08 | KM4:A1-A2 short | KM4:A1-A2 short | yes | yes | yes | yes | 6 | 0 | 2/2 | 0 | 18 | 120182 | 0.074 | 46.2 |
| h09 | KM3:5-6 stuck_open | KM3:5-6 stuck_open | yes | yes | yes | yes | 13 | 0 | 2/3 | 0 | 23 | 187485 | 0.118 | 112.8 |
| h10 | KM2:13-14 stuck_closed | insufficient_information | no | no | no | no | 3 | 0 | 2/1 | 0 | 8 | 55682 | 0.086 | 82.5 |
| h11 | KT:55-56 stuck_open | KT:55-56 stuck_open | yes | yes | yes | yes | 6 | 0 | 2/3 | 0 | 12 | 77703 | 0.051 | 41.7 |
| h12 | KM3:21-22 stuck_open | KM3:21-22 stuck_open | yes | yes | yes | yes | 12 | 1 | 2/3 | 0 | 16 | 116503 | 0.069 | 60.9 |
| h13 | SB2:13-14 stuck_closed | insufficient_information | no | no | no | no | 6 | 2 | 1/3 | 0 | 10 | 68603 | 0.090 | 78.0 |
| h14 | KK1:3-4 open | KK1:3-4 open | yes | yes | yes | yes | 17 | 0 | 1/3 | 0 | 20 | 163736 | 0.098 | 72.2 |
| h15 | KM4:21-22 stuck_open | KM4:21-22 stuck_open | yes | yes | yes | yes | 8 | 1 | 2/4 | 0 | 20 | 153888 | 0.079 | 56.8 |
| h16 | KT:67-68 stuck_open | KT:67-68 stuck_open | yes | yes | yes | yes | 5 | 0 | 1/3 | 0 | 11 | 70542 | 0.043 | 34.7 |
| h17 | KK1:1-2 open | KK1:1-2 open | yes | yes | yes | yes | 9 | 0 | 1/5 | 0 | 14 | 111409 | 0.061 | 44.8 |
| h18 | KM3:A1-A2 open | KM3:A1-A2 open | yes | yes | yes | yes | 5 | 0 | 2/2 | 0 | 22 | 167995 | 0.100 | 84.1 |
| h19 | KT:A1-A2 short | insufficient_information | no | no | no | no | 12 | 0 | 1/4 | 0 | 19 | 156020 | 0.128 | 131.4 |
| h20 | KM4 welded | KM4 welded | yes | yes | yes | yes | 8 | 0 | 1/4 | 0 | 20 | 150456 | 0.087 | 67.0 |
| h21 | HL3:X1-X2 open | HL3:X1-X2 open | yes | yes | yes | yes | 3 | 0 | 2/2 | 0 | 15 | 94376 | 0.044 | 29.7 |
| h22 | M1:W1-W2 open | M1:W1-W2 open | yes | yes | yes | yes | 3 | 0 | 2/3 | 0 | 9 | 55637 | 0.040 | 38.4 |
| h23 | QF1:1-2 open | QF1:1-2 open | yes | yes | yes | yes | 9 | 0 | 1/4 | 0 | 8 | 48727 | 0.028 | 21.1 |
| h24 | SB3:13-14 stuck_open | SB3:13-14 stuck_open | yes | yes | yes | yes | 3 | 0 | 2/1 | 0 | 6 | 34700 | 0.021 | 17.7 |
| h25 | KM1 welded | KM1 welded | yes | yes | yes | yes | 4 | 0 | 2/2 | 2 | 21 | 167579 | 0.194 | 198.9 |
| h26 | KM1:1-2 stuck_open | insufficient_information | no | no | no | no | 6 | 0 | 2/3 | 0 | 14 | 105126 | 0.077 | 69.8 |
| h27 | KM2:A1-A2 open | KM2:A1-A2 open | yes | yes | yes | yes | 5 | 0 | 3/3 | 0 | 10 | 59782 | 0.031 | 20.4 |
| h28 | KM1:A1-A2 short | KM1:A1-A2 short | yes | yes | yes | yes | 9 | 0 | 1/3 | 0 | 11 | 70882 | 0.043 | 35.6 |
| h29 | KT stuck | KT stuck | yes | yes | yes | yes | 6 | 0 | 2/4 | 0 | 18 | 140170 | 0.107 | 98.1 |
| h30 | KM4:5-6 stuck_closed | KM3:1-2 stuck_open | no | no | no | no | 16 | 0 | 2/2 | 0 | 28 | 250763 | 0.140 | 110.8 |
| l01 (latent) | KK1:95-96 stuck_closed | insufficient_information | yes | no | no | no | 7 | 0 | 4/2 | 0 | 28 | 232954 | 0.138 | 121.8 |
| l02 (latent) | KM4:21-22 stuck_closed | insufficient_information | yes | no | no | no | 5 | 0 | 5/0 | 0 | 26 | 223792 | 0.120 | 91.5 |
| l03 (latent) | KM3:3-4 stuck_closed | insufficient_information | yes | no | no | no | 6 | 0 | 6/4 | 0 | 27 | 236520 | 0.164 | 153.0 |
| l04 (latent) | HL2:X1-X2 open | HL2:X1-X2 open | yes | yes | yes | yes | 4 | 0 | 2/3 | 0 | 23 | 175941 | 0.090 | 62.0 |
| l05 (latent) | KM2:21-22 stuck_closed | insufficient_information | yes | no | no | no | 7 | 0 | 6/3 | 0 | 28 | 239692 | 0.136 | 116.2 |
| l06 (latent) | KM2:3-4 stuck_closed | insufficient_information | yes | no | no | no | 5 | 0 | 4/3 | 0 | 28 | 241123 | 0.154 | 141.2 |
| l07 (latent) | KM3:1-2 stuck_closed | insufficient_information | yes | no | no | no | 11 | 0 | 3/2 | 0 | 24 | 211179 | 0.137 | 109.0 |
| l08 (latent) | KM2:43-44 stuck_closed | insufficient_information | yes | no | no | no | 6 | 0 | 3/2 | 0 | 27 | 243461 | 0.167 | 142.7 |
| l09 (latent) | KM1:21-22 stuck_closed | KM1:21-22 stuck_closed | yes | yes | yes | yes | 3 | 0 | 2/1 | 0 | 26 | 206884 | 0.127 | 109.5 |
| l10 (latent) | KM3:5-6 stuck_closed | insufficient_information | yes | no | no | no | 6 | 0 | 6/2 | 0 | 30 | 269441 | 0.141 | 104.2 |
