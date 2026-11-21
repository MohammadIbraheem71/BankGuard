"""Eval harness scaffolding. Owner: Anum.

TODO(anum): run each dev case through gateway.handle_message in all three modes
and persist raw results under eval/results/raw/ (gitignored).
This scaffolding signature may be replaced by the owner.
NEVER read eval/cases/heldout.jsonl before code freeze.
"""
from __future__ import annotations


def run(mode: str, cases_path: str = "eval/cases/dev.jsonl") -> list[dict]:
    """Return zero results until the harness is implemented."""
    # TODO(anum): load cases, drive the gateway and collect ChatResponses.
    return []
