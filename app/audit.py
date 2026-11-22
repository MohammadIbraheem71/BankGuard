"""Audit-log recorder for executed tool calls. Owner: Ibraheem.

The gateway sets the (user_id, mode) request context via `tool_context`;
bank_api and the gateway's search_faq path call `record_tool_call` exactly once
per executed call. No contract function signature is changed by this module.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator

from . import db

_current_user_id: ContextVar[int | None] = ContextVar("bankguard_user_id", default=None)
_current_mode: ContextVar[str] = ContextVar("bankguard_mode", default="unknown")


@contextmanager
def tool_context(user_id: int, mode: str) -> Iterator[None]:
    """Bind a request's user/mode so tool modules can stamp their audit rows."""
    user_token = _current_user_id.set(user_id)
    mode_token = _current_mode.set(mode)
    try:
        yield
    finally:
        _current_user_id.reset(user_token)
        _current_mode.reset(mode_token)


def record_tool_call(name: str, args: dict, ok: bool) -> None:
    """Append one row to audit_log for a tool call that was actually executed."""
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO audit_log (ts, user_id, mode, tool_name, args_json, ok) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, _current_user_id.get(), _current_mode.get(), name, json.dumps(args, sort_keys=True), int(ok)),
        )
        conn.commit()
    finally:
        conn.close()
