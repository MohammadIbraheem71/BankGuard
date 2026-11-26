"""Offline integrity checks for committed raw runs and result tables."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_final_raw_reproduces_committed_tables() -> None:
    """Re-judging saved raw JSON must reproduce the committed CSV/Markdown tables."""
    result = subprocess.run(
        [sys.executable, "eval/check_results.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "OK: final raw files reproduce all committed result tables" in result.stdout
