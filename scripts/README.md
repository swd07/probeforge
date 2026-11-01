# Scripts

Run them from the repository root with `uv run python scripts/<name>.py` (each file's docstring has the options).
"Paid" means Meta Model API calls, checked against the local spend ledger before they start.

## Maintained commands

| Script | What it does | Paid |
|---|---|---|
| `verify_results.py` | Validates the committed ATS results offline: holdout hash and fingerprints, every row against its traces, the metrics against the JSON and the published tables | no |
| `ats_identity.py` | Offline proof that a change to frozen code leaves Hybrid v2's and the baseline's tool logs and diagnoses unchanged (D47) | no |
| `ats_results.py` | Regenerates `docs/results/ats_results.json` from the committed run records | no |
| `run_ats.py` | The agent on ATS dev cases, with a results table | yes |
| `run_ats_hybrid.py` | Hybrid v2 (or, with `--baseline`, the info-gain baseline) on ATS dev cases | yes (baseline: no) |
| `ats_explain_eval.py` | The explanation check on the 12 dev cases (D41, D42, D47); `--offline` hashes tool logs only | yes (offline: no) |
| `ats_troubleshooting.py` | Writes the troubleshooting sheet `docs/ATS_TROUBLESHOOTING.md/.json` from the simulator | no |
| `export_ats_transcription.py` | Exports the model step of a recorded hybrid run to `scenarios/transcriptions/ats/`, with the privacy check | no |
| `render_ats_sheets.py` | Renders the drawing crops the read step uses, from your local copy of the drawing (`docs/vendor/`, not in git) | no |
| `render_schematic.py` | Renders a circuit YAML to SVG (our redrawings) | no |

## Evaluation records (kept as they ran)

| Script | What it did |
|---|---|
| `ats_holdout.py` | Made and ran the S5 holdout (D45, D46). After D47 its `run` refuses to start (the fingerprints no longer match the list), as intended: the holdout is run once |
| `ats_read_eval.py`, `ats_rescore_reads.py` | Read-quality measurements of the drawing transcription (D32 to D34) |
| `ats_nextstep_identity.py` | Identity gate for the next-reading display (D39) |
| `ats_behaviour_dump.py` | Records the bench's behaviour for every fault, to prove changes to it (D35, D36) |

## Motor starter (Level 1) and early checks

| Script | What it did |
|---|---|
| `run_scenarios.py` | Agent and baselines on the motor-starter fault suites; holds the Level 1 fingerprints |
| `summarize_results.py`, `calibration.py` | Level 1 comparison tables and confidence calibration |
| `consensus_read.py`, `transcribe_schematic.py` | Level 1 schematic reading experiments |
| `screenshot_ui.py`, `screenshot_manual.py` | Level 1 UI screenshots with Playwright |
| `check_meta_api.py` | Day 1 checks of the Meta Model API (base URL, tool calling, structured output, images); it does not use the spend ledger |
