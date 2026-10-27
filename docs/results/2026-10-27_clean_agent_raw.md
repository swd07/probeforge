# Agent on clean holdout (raw table)

Run 20261027_223202_agent_clean_low.

**agent on clean (muse-spark-1.3, effort low, approvals denied), 43 runs**

- Correct: 35/43 (visible 30/38, latent 5/5)
- Component right: 30/38 visible; failure mode right: 30/38; exact incl. part: 30/38
- Measurements: 359 total, 8.3 per case; redundant 17
- Evidence items: 105 functional_test, 115 instrument_reading
- Policy blocks: 0, protocol errors: 0, tool calls recovered from text: 1, missing hypothesis updates: 79, approval requests: 11 (denied 11), errors: 0
- Tokens: 4049427, cost $2.944 ($0.068 per case)
- Time: 2344 s summed over cases, 340 s wall clock

| Case | Expected | Diagnosis | Correct | Component | Mode | Part | Meas | Redundant | Evidence F/I | Blocks | Turns | Tokens | Cost $ | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c01 | QF1:3-4 open | QF1:3-4 open | yes | yes | yes | yes | 11 | 0 | 1/4 | 0 | 12 | 80113 | 0.046 | 39.5 |
| c02 | QF1:5-6 open | insufficient_information | no | no | no | no | 9 | 0 | 2/3 | 0 | 15 | 124213 | 0.095 | 91.6 |
| c03 | FU2:1-2 open | FU2:1-2 open | yes | yes | yes | yes | 8 | 0 | 2/2 | 0 | 14 | 100509 | 0.061 | 47.0 |
| c04 | FU2:3-4 open | FU2:3-4 open | yes | yes | yes | yes | 10 | 0 | 2/3 | 0 | 12 | 79041 | 0.043 | 35.1 |
| c05 | KM1:1-2 stuck_closed | KM2 stuck_open | no | no | no | no | 6 | 0 | 4/0 | 0 | 12 | 89894 | 0.097 | 113.4 |
| c06 | KM1:3-4 stuck_open | KM1:3-4 stuck_open | yes | yes | yes | yes | 10 | 0 | 1/4 | 0 | 9 | 58599 | 0.038 | 31.8 |
| c07 | KM1:5-6 stuck_open | KM1:5-6 stuck_open | yes | yes | yes | yes | 3 | 0 | 3/1 | 0 | 10 | 66153 | 0.047 | 45.4 |
| c08 | KM1:5-6 stuck_closed | KM2:43-44 stuck_open | no | no | no | no | 13 | 2 | 3/2 | 0 | 19 | 158837 | 0.127 | 119.0 |
| c09 | KM1:13-14 stuck_closed | insufficient_information | no | no | no | no | 5 | 1 | 2/2 | 0 | 10 | 71164 | 0.099 | 90.8 |
| c10 | KM1:53-54 stuck_open | KM1:53-54 stuck_open | yes | yes | yes | yes | 3 | 0 | 2/3 | 0 | 11 | 69564 | 0.035 | 23.0 |
| c11 | KM1:21-22 stuck_open | KM1:21-22 stuck_open | yes | yes | yes | yes | 6 | 1 | 2/2 | 0 | 9 | 56135 | 0.033 | 20.9 |
| c12 | KM2 welded | KM2 welded | yes | yes | yes | yes | 9 | 1 | 2/3 | 0 | 9 | 64681 | 0.083 | 59.9 |
| c13 | KM2:A1-A2 short | KM2:A1-A2 short | yes | yes | yes | yes | 6 | 0 | 2/3 | 0 | 10 | 61714 | 0.031 | 22.9 |
| c14 | KM2:1-2 stuck_open | KM2:1-2 stuck_open | yes | yes | yes | yes | 5 | 0 | 2/3 | 0 | 13 | 92166 | 0.056 | 33.3 |
| c15 | KM2:1-2 stuck_closed | M1:V1-V2 short | no | no | no | no | 18 | 0 | 2/4 | 0 | 15 | 119281 | 0.115 | 109.8 |
| c16 | KM2:3-4 stuck_open | KM2:3-4 stuck_open | yes | yes | yes | yes | 3 | 0 | 3/2 | 0 | 9 | 57528 | 0.036 | 23.0 |
| c17 | KM2:5-6 stuck_open | KM2:5-6 stuck_open | yes | yes | yes | yes | 6 | 0 | 3/2 | 0 | 12 | 81581 | 0.049 | 29.9 |
| c18 | KM2:5-6 stuck_closed | FU2:1-2 open | no | no | no | no | 6 | 0 | 2/2 | 0 | 10 | 66953 | 0.053 | 47.7 |
| c19 | KM2:13-14 stuck_open | KM2:13-14 stuck_open | yes | yes | yes | yes | 3 | 0 | 4/1 | 0 | 8 | 50736 | 0.035 | 26.6 |
| c20 | KM2:43-44 stuck_open | KM2:43-44 stuck_open | yes | yes | yes | yes | 6 | 2 | 3/4 | 0 | 13 | 89440 | 0.057 | 40.6 |
| c21 | KM2:53-54 stuck_closed | KM2:53-54 stuck_closed | yes | yes | yes | yes | 3 | 0 | 3/3 | 0 | 12 | 78863 | 0.066 | 29.6 |
| c22 | KM2:21-22 stuck_open | KM2:21-22 stuck_open | yes | yes | yes | yes | 10 | 1 | 2/3 | 0 | 11 | 73935 | 0.039 | 20.7 |
| c23 | KM3:A1-A2 short | insufficient_information | no | no | no | no | 15 | 1 | 1/4 | 0 | 13 | 95258 | 0.100 | 93.5 |
| c24 | KM3:1-2 stuck_open | KM3:1-2 stuck_open | yes | yes | yes | yes | 12 | 0 | 1/2 | 0 | 9 | 62536 | 0.042 | 28.7 |
| c25 | KM3:3-4 stuck_open | KM3:3-4 stuck_open | yes | yes | yes | yes | 6 | 0 | 2/1 | 0 | 10 | 65009 | 0.039 | 28.7 |
| c26 | KM4:1-2 stuck_closed | KM4:1-2 stuck_closed | yes | yes | yes | yes | 3 | 0 | 2/2 | 0 | 11 | 71141 | 0.044 | 28.6 |
| c27 | KM4:3-4 stuck_open | KM4:3-4 stuck_open | yes | yes | yes | yes | 6 | 0 | 2/2 | 0 | 7 | 42785 | 0.026 | 20.9 |
| c28 | KM4:3-4 stuck_closed | KM4:3-4 stuck_closed | yes | yes | yes | yes | 6 | 0 | 2/2 | 0 | 13 | 91919 | 0.065 | 47.3 |
| c29 | KM4:5-6 stuck_open | KM4:5-6 stuck_open | yes | yes | yes | yes | 4 | 0 | 2/3 | 0 | 10 | 63060 | 0.043 | 27.9 |
| c30 | KT:55-56 stuck_closed | KT:55-56 stuck_closed | yes | yes | yes | yes | 7 | 1 | 1/4 | 0 | 6 | 38873 | 0.030 | 23.5 |
| c31 | KK1:5-6 open | KK1:5-6 open | yes | yes | yes | yes | 6 | 0 | 2/3 | 0 | 8 | 50262 | 0.037 | 31.6 |
| c32 | KK1:97-98 stuck_closed | KK1:97-98 stuck_closed | yes | yes | yes | yes | 5 | 0 | 3/4 | 0 | 13 | 88948 | 0.053 | 36.9 |
| c33 | KK1:95-96 stuck_open | KK1:95-96 stuck_open | yes | yes | yes | yes | 12 | 3 | 2/4 | 0 | 10 | 67543 | 0.042 | 27.7 |
| c34 | SB2:13-14 stuck_open | SB2:13-14 stuck_open | yes | yes | yes | yes | 9 | 1 | 2/3 | 0 | 11 | 72748 | 0.044 | 29.2 |
| c35 | SB3:13-14 stuck_closed | insufficient_information | no | no | no | no | 6 | 2 | 3/3 | 0 | 10 | 72678 | 0.090 | 74.4 |
| c36 | HL1:X1-X2 open | HL1:X1-X2 open | yes | yes | yes | yes | 3 | 1 | 3/2 | 0 | 11 | 69792 | 0.039 | 20.2 |
| c37 | M1:U1-U2 open | M1:U1-U2 open | yes | yes | yes | yes | 15 | 0 | 2/4 | 0 | 20 | 164836 | 0.118 | 89.8 |
| c38 | M1:V1-V2 open | M1:V1-V2 open | yes | yes | yes | yes | 11 | 0 | 1/4 | 0 | 12 | 83749 | 0.058 | 40.5 |
| cl01 (latent) | KM1:3-4 stuck_closed | insufficient_information | yes | no | no | no | 21 | 0 | 5/2 | 0 | 26 | 233789 | 0.147 | 110.2 |
| cl02 (latent) | KM1:43-44 stuck_closed | insufficient_information | yes | no | no | no | 16 | 0 | 2/4 | 0 | 20 | 168250 | 0.143 | 121.9 |
| cl03 (latent) | KM3:21-22 stuck_closed | insufficient_information | yes | no | no | no | 15 | 0 | 4/2 | 0 | 21 | 178069 | 0.133 | 112.9 |
| cl04 (latent) | KT:67-68 stuck_closed | insufficient_information | yes | no | no | no | 11 | 0 | 6/2 | 0 | 26 | 236866 | 0.168 | 140.3 |
| cl05 (latent) | KK1:97-98 stuck_open | insufficient_information | yes | no | no | no | 11 | 0 | 5/2 | 0 | 26 | 240216 | 0.141 | 108.2 |
