# Run records cited by the docs

Copies of the run folders that README.md, docs/results/ats_results.md and DECISIONS.md cite (the working folder
`runs/` is not in the repository). JSON traces as written by the scripts: every tool call with its policy verdict and
result, the model turns with token counts and cost, the diagnosis. They contain no drawing images, no API keys and
nothing from the submittal's cover pages (checked before committing). The Hybrid v2 netlists in them are Muse Spark's
transcriptions of crops of the original ASCO drawing 978741 (drawing areas only, never committed; see "What each
diagnostician sees" in docs/ATS_MODEL.md). The agent traces were made from our own redrawing (an image rendered from
our netlist) and the text netlist.

| Folder | What | Cited in |
|---|---|---|
| [20261031_123544_ats_holdout](20261031_123544_ats_holdout/) | S5 holdout, 28 cases: `results.json`, per-case traces for the agent, Hybrid v2 and the baseline, `run_log.txt` | [D46](../../DECISIONS.md#d46-s5-holdout-run-and-results-2026-10-31), [results](../../docs/results/ats_results.md) |
| [20261031_012952_ats_agent_chat_low](20261031_012952_ats_agent_chat_low/) | Agent on the 12 dev cases, Chat Completions, low effort (the dev agent column) | [D38](../../DECISIONS.md#d38-keep-chat-completions-for-the-ats-agent-2026-10-31) |
| [20261031_013347_ats_agent_responses_low](20261031_013347_ats_agent_responses_low/) | The same with the Responses transport | [D38](../../DECISIONS.md#d38-keep-chat-completions-for-the-ats-agent-2026-10-31) |
| [20261030_174105_ats_agent_low](20261030_174105_ats_agent_low/) | First 5-case agent smoke test on the ATS bench | DECISIONS.md |
| [20261030_222622_ats_reads](20261030_222622_ats_reads/) | Three saved Muse Spark reads of the drawing sheets | the saved-read hybrid runs |
| [20261031_003748_ats_hybrid](20261031_003748_ats_hybrid/) | Hybrid v2 on the saved reads: two accepted repairs, 5/5 dev cases (the freeze run; the default saved transcription comes from it) | [D34](../../DECISIONS.md#d34-hybrid-v2-frozen-2026-10-31) |
| [20261031_004956_ats_hybrid](20261031_004956_ats_hybrid/) | Hybrid v2 with three fresh reads in the run, 5/5 dev cases (the second saved transcription) | DECISIONS.md |
| [20261031_114432_ats_explain_d42_after2](20261031_114432_ats_explain_d42_after2/) | Explanation check on the 12 dev cases after D42 (the dev Hybrid v2 column) | [D42](../../DECISIONS.md#d42-explanation-rule-for-consequential-faults-the-root-cause-first-then-the-damaged-part-2026-10-31) |
| [20261101_105210_ats_explain_d47_after](20261101_105210_ats_explain_d47_after/) | Explanation check on the 12 dev cases after the post-holdout fixes | [D47](../../DECISIONS.md#d47-post-holdout-fixes-to-frozen-ats-code-2026-11-01) |
| [20261101_105449_ats_agent_chat_low](20261101_105449_ats_agent_chat_low/) | Post-fix agent smoke check on 5 dev cases (a check, not a result) | [D47](../../DECISIONS.md#d47-post-holdout-fixes-to-frozen-ats-code-2026-11-01) |

The offline identity records of D47 are in [../identity/](../identity/).
