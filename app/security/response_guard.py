"""Outbound response guard. Owner: Muzammil.

TODO(muzammil): redact canaries/PII and compare claims to verified_facts.
"""
from __future__ import annotations

from app.models import GuardResult, User


def check(user: User, text: str, verified_facts: dict | None = None) -> GuardResult:
    """Permissive placeholder: mark everything safe and leave text unchanged."""
    # TODO(muzammil): implement redaction; summary strings must never leak secrets.
    return GuardResult(safe=True, text=text, findings=[])
