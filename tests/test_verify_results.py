"""The offline results check (scripts/verify_results.py) passes on the committed records and fails when a published
number is changed."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_results  # noqa: E402


def test_committed_results_verify(capsys):
    verify_results.problems.clear()
    verify_results.main()
    assert "all committed results verified" in capsys.readouterr().out


def test_a_changed_published_number_fails(tmp_path, monkeypatch):
    text = verify_results.README.read_text(encoding="utf-8")
    changed = text.replace("| Part-level correct | 10/12 | 17/28 |", "| Part-level correct | 10/12 | 19/28 |")
    assert changed != text
    fake = tmp_path / "README.md"
    fake.write_text(changed, encoding="utf-8")
    monkeypatch.setattr(verify_results, "README", fake)
    verify_results.problems.clear()
    with pytest.raises(SystemExit):
        verify_results.main()
    assert any("Part-level correct / Agent holdout" in p for p in verify_results.problems)
