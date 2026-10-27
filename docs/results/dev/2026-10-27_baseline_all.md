# [dev] Half-split baseline on s01-s08 + holdout (2026-10-27)

Run 20261027_215736_baseline_all. Deterministic: one run is enough.

**baseline on all (half-split baseline), 48 runs**

- Correct: 40/48 (visible 30/38, latent 10/10)
- Component right: 31/38 visible; failure mode right: 30/38; exact incl. part: 29/38
- Measurements: 444 total, 9.2 per case; redundant 32
- Evidence items: 32 functional_test, 172 instrument_reading
- Policy blocks: 0, protocol errors: 0, errors: 0
- Tokens: 0, cost $0.000 ($0.000 per case)
- Time: 0 s summed over cases, 1 s wall clock

| Case | Expected | Diagnosis | Correct | Component | Mode | Part | Meas | Redundant | Evidence F/I | Blocks | Turns | Tokens | Cost $ | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s01 | FU1:1-2 open | FU1:1-2 open | yes | yes | yes | yes | 3 | 1 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| s02 | SB1:11-12 stuck_open | SB1:11-12 stuck_open | yes | yes | yes | yes | 4 | 0 | 2/4 | 0 | 0 | 0 | 0.000 | 0.0 |
| s03 | KK1 tripped | KK1 tripped | yes | yes | yes | yes | 1 | 0 | 1/1 | 0 | 0 | 0 | 0.000 | 0.0 |
| s04 | KM1:A1-A2 open | KM1:A1-A2 open | yes | yes | yes | yes | 3 | 0 | 2/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| s05 | KM1:13-14 stuck_open | KM1:13-14 stuck_open | yes | yes | yes | yes | 0 | 0 | 2/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| s06 | KT:A1-A2 open | KT:A1-A2 open | yes | yes | yes | yes | 10 | 2 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| s07 | KM3 welded | KM3 welded | yes | yes | yes | yes | 8 | 1 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| s08 | FU2:5-6 open | FU2:5-6 open | yes | yes | yes | yes | 3 | 0 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| h01 | KM1:53-54 stuck_closed | KM1:13-14 stuck_closed | yes | yes | yes | no | 13 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h02 | KM4:1-2 stuck_open | insufficient_information | no | no | no | no | 57 | 4 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h03 | HL4:X1-X2 open | HL4:X1-X2 open | yes | yes | yes | yes | 6 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h04 | KM1:43-44 stuck_open | KM1:43-44 stuck_open | yes | yes | yes | yes | 3 | 0 | 2/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| h05 | KM2:53-54 stuck_open | KM2:53-54 stuck_open | yes | yes | yes | yes | 11 | 4 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h06 | SB1:11-12 stuck_closed | insufficient_information | no | no | no | no | 52 | 4 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h07 | KM4:A1-A2 open | KM4:A1-A2 open | yes | yes | yes | yes | 35 | 2 | 0/6 | 0 | 0 | 0 | 0.000 | 0.1 |
| h08 | KM4:A1-A2 short | KM4:A1-A2 short | yes | yes | yes | yes | 2 | 0 | 1/2 | 0 | 0 | 0 | 0.000 | 0.0 |
| h09 | KM3:5-6 stuck_open | insufficient_information | no | no | no | no | 57 | 4 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h10 | KM2:13-14 stuck_closed | KM1:13-14 stuck_closed | no | no | no | no | 13 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h11 | KT:55-56 stuck_open | KT:55-56 stuck_open | yes | yes | yes | yes | 10 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h12 | KM3:21-22 stuck_open | KM3:21-22 stuck_open | yes | yes | yes | yes | 8 | 1 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h13 | SB2:13-14 stuck_closed | KM1:A1-A2 short | no | no | no | no | 9 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h14 | KK1:3-4 open | KK1:3-4 open | yes | yes | yes | yes | 3 | 0 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| h15 | KM4:21-22 stuck_open | KM4:21-22 stuck_open | yes | yes | yes | yes | 8 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h16 | KT:67-68 stuck_open | KT:67-68 stuck_open | yes | yes | yes | yes | 10 | 2 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h17 | KK1:1-2 open | KK1:1-2 open | yes | yes | yes | yes | 3 | 0 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| h18 | KM3:A1-A2 open | KM1:43-44 stuck_open | no | no | no | no | 19 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h19 | KT:A1-A2 short | KM3:A1-A2 short | no | no | no | no | 2 | 0 | 1/2 | 0 | 0 | 0 | 0.000 | 0.0 |
| h20 | KM4 welded | KM4 welded | yes | yes | yes | yes | 8 | 1 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h21 | HL3:X1-X2 open | HL3:X1-X2 open | yes | yes | yes | yes | 6 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h22 | M1:W1-W2 open | M1:W1-W2 open | yes | yes | yes | yes | 2 | 0 | 1/2 | 0 | 0 | 0 | 0.000 | 0.0 |
| h23 | QF1:1-2 open | QF1:1-2 open | yes | yes | yes | yes | 3 | 1 | 1/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| h24 | SB3:13-14 stuck_open | SB3:13-14 stuck_open | yes | yes | yes | yes | 5 | 0 | 1/5 | 0 | 0 | 0 | 0.000 | 0.0 |
| h25 | KM1 welded | KM1:A1-A2 short | no | yes | no | no | 9 | 0 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h26 | KM1:1-2 stuck_open | KM1:1-2 stuck_open | yes | yes | yes | yes | 5 | 0 | 1/5 | 0 | 0 | 0 | 0.000 | 0.0 |
| h27 | KM2:A1-A2 open | KM2:A1-A2 open | yes | yes | yes | yes | 3 | 0 | 2/3 | 0 | 0 | 0 | 0.000 | 0.0 |
| h28 | KM1:A1-A2 short | KM1:A1-A2 short | yes | yes | yes | yes | 1 | 0 | 1/1 | 0 | 0 | 0 | 0.000 | 0.0 |
| h29 | KT stuck | KT stuck | yes | yes | yes | yes | 10 | 2 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| h30 | KM4:5-6 stuck_closed | KM4:5-6 stuck_closed | yes | yes | yes | yes | 39 | 3 | 0/6 | 0 | 0 | 0 | 0.000 | 0.0 |
| l01 (latent) | KK1:95-96 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| l02 (latent) | KM4:21-22 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| l03 (latent) | KM3:3-4 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| l04 (latent) | HL2:X1-X2 open | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| l05 (latent) | KM2:21-22 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| l06 (latent) | KM2:3-4 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| l07 (latent) | KM3:1-2 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| l08 (latent) | KM2:43-44 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| l09 (latent) | KM1:21-22 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
| l10 (latent) | KM3:5-6 stuck_closed | insufficient_information | yes | no | no | no | 0 | 0 | 1/0 | 0 | 0 | 0 | 0.000 | 0.0 |
