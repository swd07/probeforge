# Confidence calibration (2026-10-28)

Every submitted agent diagnosis in the saved batch runs, bucketed by the confidence the agent stated in
submit_diagnosis. Correct = component and failure mode match the injected fault. insufficient_information
answers are left out (no claim). Each run of a repeated case counts separately.

## All agent runs (dev and clean, muse-spark-1.3)

| Stated confidence | Diagnoses | Correct | Accuracy | Mean stated confidence |
|---|---|---|---|---|
| below 70% | 3 | 0 | 0% | 65% |
| 70 to 90% | 10 | 3 | 30% | 79% |
| 90% and above | 239 | 223 | 93% | 95% |
| all | 252 | 226 | 90% | 94% |

## Clean holdout runs only (with the schematic image)

| Stated confidence | Diagnoses | Correct | Accuracy | Mean stated confidence |
|---|---|---|---|---|
| below 70% | 2 | 0 | 0% | 65% |
| 70 to 90% | 9 | 3 | 33% | 80% |
| 90% and above | 62 | 55 | 89% | 95% |
| all | 73 | 58 | 79% | 92% |

Runs used (14): 20261027_212845_low, 20261027_212923_low, 20261027_212925_medium, 20261027_215747_agent_holdout_low, 20261027_215748_agent_scenarios_low, 20261027_220753_agent_holdout_low, 20261027_220754_agent_scenarios_low, 20261027_222844_agent_scenarios_low, 20261027_223202_agent_clean_low, 20261027_223203_agent_dev_low, 20261027_223346_agent_dev_low_approve, 20261027_223811_agent_clean_low, 20261027_223813_agent_clean_low_approve, 20261028_095705_agent_clean_low_noimage
