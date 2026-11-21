"""Tool-call policy engine. Owner: Muzammil.

TODO(muzammil): enforce per-user account ownership and cross-account rules.
"""
from __future__ import annotations

from app.models import PolicyDecision, ToolCall, User


def authorize(user: User, call: ToolCall) -> PolicyDecision:
    """Permissive placeholder: allow every call; require confirmation to transfer."""
    # TODO(muzammil): replace this with the real policy rules.
    return PolicyDecision(
        allowed=True,
        reason="placeholder policy allows all tool calls",
        requires_confirmation=(call.name == "create_transfer"),
    )
