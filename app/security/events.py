"""Security event storage. Owner: Muzammil.

TODO(muzammil): enforce redaction of `summary` before it reaches the database.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app import db
from app.models import SecurityEvent


def log_event(user_id, mode, event_type, severity, summary, details) -> None:
    """Append one security event to the SQLite security_events table."""
    # TODO(muzammil): redact summaries and reject unexpected severity values.
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO security_events (ts, user_id, mode, event_type, severity, summary, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, user_id, mode, event_type, severity, summary, json.dumps(details, sort_keys=True)),
        )
        conn.commit()
    finally:
        conn.close()


def list_events(limit: int = 200, mode: str | None = None) -> list[SecurityEvent]:
    """Return the most recent security events, optionally filtered by mode."""
    conn = db.get_conn()
    try:
        if mode is None:
            rows = conn.execute(
                "SELECT ts, user_id, mode, event_type, severity, summary, details_json "
                "FROM security_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT ts, user_id, mode, event_type, severity, summary, details_json "
                "FROM security_events WHERE mode = ? ORDER BY id DESC LIMIT ?",
                (mode, limit),
            ).fetchall()
    finally:
        conn.close()
    return [
        SecurityEvent(
            ts=row["ts"],
            user_id=row["user_id"],
            mode=row["mode"],
            event_type=row["event_type"],
            severity=row["severity"],
            summary=row["summary"],
            details=json.loads(row["details_json"]),
        )
        for row in rows
    ]
