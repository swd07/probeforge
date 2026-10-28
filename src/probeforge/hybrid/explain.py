"""Explain step: Muse Spark writes a short technician-facing explanation of the planner's result."""

import re

from probeforge.hybrid.llm import Usage, action_text, chat, outcome_text

PROMPT = """You are writing for the technician who will repair this motor starter ({title}). A diagnostic
planner took the readings below on the real machine and reached this result:

{result}

Readings (step: action -> real outcome | what a healthy circuit gives | candidate faults ruled out):
{history}

Components: {components}
{corrections}
Write a short explanation in plain text (3 to 6 sentences, no lists, no headings): what is faulty and
where, which readings prove it (cite the decisive ones as "step N" and give the measured value next to
what a healthy circuit reads), and what to check or replace. If the result is insufficient
information, say which faults remain possible, what was ruled out, and what the technician should
check next. Use only the readings listed."""


def result_text(diagnosis: dict, left: list[str]) -> str:
    if diagnosis.get("outcome") == "diagnosed":
        part = f" part {diagnosis['part']}" if diagnosis.get("part") else ""
        return (f"diagnosed: {diagnosis['component']}{part} {diagnosis['failure_mode']} "
                f"(confidence {diagnosis.get('confidence')})")
    return f"insufficient information; candidate faults still possible: {', '.join(left[:12]) or 'none'}"


def explain(client, usage: Usage, planner, diagnosis: dict, effort: str = "low") -> tuple[str, list[int]]:
    healthy = planner.healthy_outcomes()
    lines = []
    for h, ok in zip(planner.history, healthy):
        ruled = h["before"] - h.get("after", h["before"])
        lines.append(f"  {h['step']}: {action_text(h['tool'], h['args'])} -> {outcome_text(h['tool'], h['actual'])}"
                     f" | {outcome_text(h['tool'], ok)} | {ruled}")
    corrections = ""
    if planner.corrections:
        n = len(planner.corrections)
        corrections = (f"\nNote: the schematic transcription was corrected {n} time(s) during the diagnosis because "
                       "readings contradicted it; the readings above are real.\n")
    n = planner.n
    text = PROMPT.format(title=n.title, result=result_text(diagnosis, [str(f) for f in planner.faults_left]),
                         history="\n".join(lines),
                         components=", ".join(f"{c.id} ({c.label})" for c in n.components.values()),
                         corrections=corrections)
    reply = chat(client, usage, "explanation", text, None, effort).strip()
    steps = {h["step"] for h in planner.history}
    cited = sorted({int(s) for s in re.findall(r"\bsteps? (\d+)", reply)} & steps)
    return reply, cited
