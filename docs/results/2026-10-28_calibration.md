# Confidence calibration (2026-10-28)

Every submitted agent diagnosis in the saved batch runs, bucketed by the confidence the agent stated in
submit_diagnosis. Correct = pole level: component, failure mode and part match the injected fault (rescored
from the saved diagnoses, so every run uses the same definition). insufficient_information
answers are left out (no claim). Each run of a repeated case counts separately.

## All agent runs (dev and clean, muse-spark-1.3)

| Stated confidence | Diagnoses | Correct | Accuracy | Mean stated confidence |
|---|---|---|---|---|
| below 70% | 3 | 0 | 0% | 65% |
| 70 to 90% | 14 | 3 | 21% | 80% |
| 90% and above | 269 | 248 | 92% | 95% |
| all | 286 | 251 | 88% | 94% |

## Clean holdout runs only (with the schematic image)

| Stated confidence | Diagnoses | Correct | Accuracy | Mean stated confidence |
|---|---|---|---|---|
| below 70% | 2 | 0 | 0% | 65% |
| 70 to 90% | 13 | 3 | 23% | 81% |
| 90% and above | 92 | 82 | 89% | 95% |
| all | 107 | 85 | 79% | 93% |

Runs used (15): 20261027_212845_low, 20261027_212923_low, 20261027_212925_medium, 20261027_215747_agent_holdout_low, 20261027_215748_agent_scenarios_low, 20261027_220753_agent_holdout_low, 20261027_220754_agent_scenarios_low, 20261027_222844_agent_scenarios_low, 20261027_223202_agent_clean_low, 20261027_223203_agent_dev_low, 20261027_223346_agent_dev_low_approve, 20261027_223811_agent_clean_low, 20261027_223813_agent_clean_low_approve, 20261028_095705_agent_clean_low_noimage, 20261028_122742_agent_clean_low_nonetlist
