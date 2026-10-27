# Dev results (not a clean test)

Every run in this folder was made while the agent prompt and the baseline rules were still being changed, with these
faults and their results visible: the 8 hand-written scenarios (s01-s08) and the dev holdout (scenarios/holdout_dev.yaml).
They also predate the sequence-based motor model, so welded delta-contactor poles show the old "stopped, zero current"
behaviour. Use them to follow the development, not as evidence of how well the agent generalizes.

The reported numbers come from the clean holdout (scenarios/holdout_clean.yaml) in docs/results/.
