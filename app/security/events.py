"""Persist and list security events using fixed summaries and typed metadata."""
from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timezone
from typing import get_args

from app import db
from app.config import Mode
from app.models import SecurityEvent, ToolName

from .response_guard import FINDINGS

_SUMMARIES = {
    "blocked_user_message": "Blocked: user message flagged",
    "blocked_document": "Blocked: retrieved document flagged",
    "policy_denied": "Denied: tool call rejected by policy",
    "transfer_pending": "Pending transfer awaits user confirmation",
    "response_guard_blocked": "Blocked: outbound reply marked unsafe",
    "chat_completed": "Chat handled in full mode",
    "security_event": "Security event recorded",
}
_MODES = frozenset(mode.value for mode in Mode)
_SEVERITIES = frozenset({"low", "medium", "high"})
_TOOLS = frozenset(get_args(ToolName))
_CATEGORIES = frozenset({
    "instruction_override", "role_impersonation", "data_extraction",
    "embedded_document_instruction", "obfuscation",
})
_LIST_FIELDS = {"categories": _CATEGORIES, "tools": _TOOLS, "findings": FINDINGS}


def _event_type(value: str) -> str:
    return value if value in _SUMMARIES else "security_event"


def _safe_details(details) -> dict:
    if not isinstance(details, dict):
        return {}

    safe = {}
    for key, allowed in _LIST_FIELDS.items():
        values = details.get(key)
        if isinstance(values, list):
            safe[key] = [value for value in values if isinstance(value, str) and value in allowed]
    tool = details.get("tool")
    if isinstance(tool, str) and tool in _TOOLS:
        safe["tool"] = tool
    blocked = details.get("blocked")
    if isinstance(blocked, bool):
        safe["blocked"] = blocked
    return safe


def log_event(user_id, mode, event_type, severity, summary, details) -> None:
    """Record a security event using a summary derived from its type."""
    if mode not in _MODES or severity not in _SEVERITIES:
        raise ValueError("Invalid security event mode or severity.")
    event_type = _event_type(event_type)
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with closing(db.get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO security_events (ts, user_id, mode, event_type, severity, summary, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, user_id, mode, event_type, severity, _SUMMARIES[event_type],
             json.dumps(_safe_details(details), sort_keys=True)),
        )


def list_events(limit: int = 200, mode: str | None = None) -> list[SecurityEvent]:
    """Return the most recent events using the same redaction rules as writes."""
    query = "SELECT ts, user_id, mode, event_type, severity, details_json FROM security_events"
    limit = min(max(0, limit), 2**63 - 1)
    with closing(db.get_conn()) as conn:
        if mode is None:
            rows = conn.execute(query + " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        else:
            rows = conn.execute(query + " WHERE mode = ? ORDER BY id DESC LIMIT ?", (mode, limit)).fetchall()

    result = []
    for row in rows:
        event_type = _event_type(row["event_type"])
        try:
            details = json.loads(row["details_json"])
        except (TypeError, ValueError):
            details = {}
        result.append(SecurityEvent(
            ts=row["ts"],
            user_id=row["user_id"],
            mode=row["mode"] if row["mode"] in _MODES else "unknown",
            event_type=event_type,
            severity=row["severity"] if row["severity"] in _SEVERITIES else "low",
            summary=_SUMMARIES[event_type],
            details=_safe_details(details),
        ))
    return result
