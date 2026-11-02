"""Run inside the image (CI and docs/DEPLOY.md): every path the server reads at run time is there, nothing that must
stay out is, and the runtime is not root and has no build tools.

    docker run --rm probeforge:latest python deploy/check_image.py      (the CI copies it in with -v)
"""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path("/app")
# every path the server reads at run time (docs/DEPLOY.md, "What the image contains")
NEEDED = [
    "src/probeforge/server/app.py",
    "scenarios/circuits/asco_300g_978741.yaml",
    "scenarios/circuits/star_delta_reversing.yaml",
    "scenarios/ats",  # the 12 dev cases
    "scenarios/transcriptions/ats/run_20261031_003748.yaml",  # the default saved Hybrid read
    "scenarios/transcriptions/ats/run_20261031_004956.yaml",
    "scenarios/transcriptions/star_delta_run2.yaml",
    "scenarios/transcriptions/star_delta_photo_run3.yaml",
    "scenarios/photos/star_delta_phone.jpg",
    "scenarios/s01_control_fuse_blown.yaml",
    "scenarios/holdout_clean.yaml",
    "scenarios/engineer_traces",
    "results/runs",  # the never-tier count at startup
    "docs/ATS_TROUBLESHOOTING.json",
    "web/dist/index.html",
    "runs",  # the volume
]
ABSENT = [".env", "docs/vendor", "docs/NEXT_STEPS.md", "tests", "scripts", ".git", "node_modules", "web/src"]

problems = [f"missing: {p}" for p in NEEDED if not (ROOT / p).exists()]
problems += [f"must not be in the image: {p}" for p in ABSENT if (ROOT / p).exists()]
problems += [f"build tool in the runtime: {t}" for t in ("uv", "node", "npm", "gcc", "pip") if shutil.which(t)]
if os.getuid() == 0:
    problems.append("runs as root")
if not os.access(ROOT / "runs", os.W_OK):
    problems.append("runs/ is not writable")
if len(list((ROOT / "scenarios" / "ats").glob("*.yaml"))) != 12:
    problems.append("not 12 dev cases")
print("\n".join(problems) or f"image ok: {len(NEEDED)} runtime paths present, {len(ABSENT)} excluded, uid {os.getuid()}")
sys.exit(1 if problems else 0)
