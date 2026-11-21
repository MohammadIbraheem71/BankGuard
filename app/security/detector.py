"""Prompt-injection detector. Owner: Muzammil.

TODO(muzammil): detect instruction_override, role_impersonation,
data_extraction, embedded_document_instruction and obfuscation.
"""
from __future__ import annotations

from typing import Literal

from app.models import DetectionResult


def inspect(text: str, source: Literal["user", "document"] = "user") -> DetectionResult:
    """Permissive placeholder: never flags user or document text."""
    # TODO(muzammil): implement the real detector, keeping score within 0..1.
    return DetectionResult(flagged=False, score=0.0, categories=[], reasons=[])
