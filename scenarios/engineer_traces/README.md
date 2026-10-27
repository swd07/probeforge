# Engineer reference traces

Recorded in the web UI's Engineer mode: a human runs the same tools under the same safety policy as the
agent, and submits a diagnosis. Each `*.json` file is a run trace in the same format as agent runs
(`tool_log`, `measurements`, `redundant_measurements`, `policy`, ...), plus `engineer`, `fault`,
`verdict` and `recorded`.

These files name the injected fault, which is fine because no agent ever reads this folder. They form
the engineer column next to the agent and the baseline (`src/probeforge/eval/engineer.py`,
`scripts/summarize_results.py`).

Only traces from real engineers belong here; scripted UI demos are not engineer references.
