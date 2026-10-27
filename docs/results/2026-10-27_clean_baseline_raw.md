# Baseline on clean holdout (raw table)

Run 20261027_222842_baseline_clean.

**baseline on clean (half-split baseline, approvals denied), 43 runs**

- Correct: 30/43 (visible 25/38, latent 5/5)
- Component right: 26/38 visible; failure mode right: 25/38; exact incl. part: 25/38
- Measurements: 472 total, 11.0 per case; redundant 29
- Evidence items: 26 functional_test, 171 instrument_reading
- Policy blocks: 0, protocol errors: 0, tool calls recovered from text: 0, missing hypothesis updates: 0, approval requests: 0 (denied 0), errors: 0
- Tokens: 0, cost $0.000 ($0.000 per case)
- Time: 0 s summed over cases, 1 s wall clock

| Case | Expected | Diagnosis | Correct | Component | Mode | Part | Meas | Redundant | Evidence F/I | Blocks | Turns | Tokens | Cost $ | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c01 | QF1:3-4 open | QF1:3-4 open | yes | yes | yes | yes | 3 | 0 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| c02 | QF1:5-6 open | QF1:5-6 open | yes | yes | yes | yes | 3 | 0 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| c03 | FU2:1-2 open | FU2:1-2 open | yes | yes | yes | yes | 3 | 0 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| c04 | FU2:3-4 open | FU2:3-4 open | yes | yes | yes | yes | 3 | 0 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| c05 | KM1:1-2 stuck_closed | FU2:1-2 open | no | no | no | no | 9 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c06 | KM1:3-4 stuck_open | KM1:3-4 stuck_open | yes | yes | yes | yes | 5 | 0 | 1/5 | 0 | 0 | 0 | 0.000 | 0.0 |
| c07 | KM1:5-6 stuck_open | KM1:5-6 stuck_open | yes | yes | yes | yes | 5 | 0 | 1/5 | 0 | 0 | 0 | 0.000 | 0.0 |
| c08 | KM1:5-6 stuck_closed | FU2:1-2 open | no | no | no | no | 9 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c09 | KM1:13-14 stuck_closed | KM1:A1-A2 short | no | yes | no | no | 9 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c10 | KM1:53-54 stuck_open | KM1:53-54 stuck_open | yes | yes | yes | yes | 11 | 4 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c11 | KM1:21-22 stuck_open | KM1:21-22 stuck_open | yes | yes | yes | yes | 6 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c12 | KM2 welded | KM1:3-4 stuck_closed | no | no | no | no | 12 | 1 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c13 | KM2:A1-A2 short | KM2:A1-A2 short | yes | yes | yes | yes | 1 | 0 | 1/1 | 0 | 0 | 0 | 0.000 | 0.0 |
| c14 | KM2:1-2 stuck_open | KM2:1-2 stuck_open | yes | yes | yes | yes | 5 | 0 | 1/5 | 0 | 0 | 0 | 0.000 | 0.0 |
| c15 | KM2:1-2 stuck_closed | FU2:1-2 open | no | no | no | no | 9 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c16 | KM2:3-4 stuck_open | KM2:3-4 stuck_open | yes | yes | yes | yes | 5 | 0 | 1/5 | 0 | 0 | 0 | 0.000 | 0.0 |
| c17 | KM2:5-6 stuck_open | KM2:5-6 stuck_open | yes | yes | yes | yes | 5 | 0 | 1/5 | 0 | 0 | 0 | 0.000 | 0.0 |
| c18 | KM2:5-6 stuck_closed | FU2:1-2 open | no | no | no | no | 9 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c19 | KM2:13-14 stuck_open | KM2:13-14 stuck_open | yes | yes | yes | yes | 0 | 0 | 2/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| c20 | KM2:43-44 stuck_open | KM2:43-44 stuck_open | yes | yes | yes | yes | 3 | 0 | 2/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| c21 | KM2:53-54 stuck_closed | KM1:13-14 stuck_closed | no | no | no | no | 13 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c22 | KM2:21-22 stuck_open | KM2:21-22 stuck_open | yes | yes | yes | yes | 6 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c23 | KM3:A1-A2 short | KM3:A1-A2 short | yes | yes | yes | yes | 2 | 0 | 1/2 | 0 | 0 | 0 | 0.000 | 0.0 |
| c24 | KM3:1-2 stuck_open | insufficient_information | no | no | no | no | 53 | 5 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c25 | KM3:3-4 stuck_open | insufficient_information | no | no | no | no | 53 | 5 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c26 | KM4:1-2 stuck_closed | KM4:1-2 stuck_closed | yes | yes | yes | yes | 37 | 2 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c27 | KM4:3-4 stuck_open | insufficient_information | no | no | no | no | 57 | 4 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c28 | KM4:3-4 stuck_closed | KM4:3-4 stuck_closed | yes | yes | yes | yes | 38 | 3 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c29 | KM4:5-6 stuck_open | insufficient_information | no | no | no | no | 57 | 4 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c30 | KT:55-56 stuck_closed | KM3:21-22 stuck_open | no | no | no | no | 8 | 1 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c31 | KK1:5-6 open | KK1:5-6 open | yes | yes | yes | yes | 3 | 0 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| c32 | KK1:97-98 stuck_closed | KK1:97-98 stuck_closed | yes | yes | yes | yes | 1 | 0 | 1/1 | 0 | 0 | 0 | 0.000 | 0.0 |
| c33 | KK1:95-96 stuck_open | KK1:95-96 stuck_open | yes | yes | yes | yes | 6 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c34 | SB2:13-14 stuck_open | SB2:13-14 stuck_open | yes | yes | yes | yes | 5 | 0 | 1/5 | 0 | 0 | 0 | 0.000 | 0.0 |
| c35 | SB3:13-14 stuck_closed | KM1:13-14 stuck_closed | no | no | no | no | 13 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| c36 | HL1:X1-X2 open | HL1:X1-X2 open | yes | yes | yes | yes | 1 | 0 | 1/1 | 0 | 0 | 0 | 0.000 | 0.0 |
| c37 | M1:U1-U2 open | M1:U1-U2 open | yes | yes | yes | yes | 2 | 0 | 1/2 | 0 | 0 | 0 | 0.000 | 0.0 |
| c38 | M1:V1-V2 open | M1:V1-V2 open | yes | yes | yes | yes | 2 | 0 | 1/2 | 0 | 0 | 0 | 0.000 | 0.0 |
| cl01 (latent) | KM1:3-4 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.1 |
| cl02 (latent) | KM1:43-44 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.1 |
| cl03 (latent) | KM3:21-22 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| cl04 (latent) | KT:67-68 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| cl05 (latent) | KK1:97-98 stuck_open | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
