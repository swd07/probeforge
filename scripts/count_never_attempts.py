"""Count the never-tier attempts in the committed ATS runs (results/runs), per runner.

    python -m uv run python scripts/count_never_attempts.py
"""

from pathlib import Path

from probeforge.eval.never_attempts import count

ROOT = Path(__file__).resolve().parents[1] / "results" / "runs"

if __name__ == "__main__":
    for runner, c in count(ROOT).items():
        print(f"{runner}: {c['never']} never-tier attempts in {c['runs']} runs ({c['steps']} logged steps)")
