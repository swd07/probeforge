"""File names from visitor input and folder size limits for the server (audit S5)."""

import re
from pathlib import Path

KEEP_FILES = 200  # newest files kept in a growing folder (visitor traces, Compare results)


def slug(text: str, limit: int = 40) -> str:
    """Letters, digits and dashes only, so typed text can never leave its folder or break the file name."""
    return (re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-") or "x")[:limit]


def prune(folder: Path, keep: int = KEEP_FILES) -> None:
    """Keep the newest `keep` JSON files of a folder (by name: they start with a time stamp or end with one)."""
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for p in files[:-keep] if len(files) > keep else []:
        p.unlink(missing_ok=True)
