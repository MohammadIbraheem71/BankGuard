"""Raw banking tools with NO authorization. Owner: Ibraheem.

These tools intentionally trust the account id supplied by the caller; the
policy engine (app/security/policy.py) is responsible for authorization.
Every call that reaches execution writes exactly one audit_log row, which is
the ground truth used by the eval harness.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator

from . import db
from .audit import _insert_tool_call, record_tool_call
from .models import ToolResult


def _record(name: str, args: dict, result: ToolResult) -> ToolResult:
    """Stamp the audit row for one executed call and return the result."""
    record_tool_call(name, args, result.ok)
    return result


def get_balance(account_id: int) -> ToolResult:
    """Return the raw balance for any account id, authorized or not."""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id, balance FROM accounts WHERE id = ?", (account_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return _record("get_balance", {"account_id": account_id},
                       ToolResult(ok=False, data={}, error="Account not found"))
    return _record(
        "get_balance",
        {"account_id": account_id},
        ToolResult(ok=True, data={"account_id": row["id"], "balance": row["balance"]}, error=None),
    )


def get_transactions(account_id: int, limit: int = 10) -> ToolResult:
    """Return the most recent transactions for any account id."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT id, ts, description, amount FROM transactions "
            "WHERE account_id = ? ORDER BY ts DESC, id DESC LIMIT ?",
            (account_id, limit),
        ).fetchall()
    finally:
        conn.close()
    transactions = [
        {"id": row["id"], "ts": row["ts"], "description": row["description"], "amount": row["amount"]}
        for row in rows
    ]
    return _record(
        "get_transactions",
        {"account_id": account_id, "limit": limit},
        ToolResult(ok=True, data={"account_id": account_id, "transactions": transactions}, error=None),
    )


_transfer_connection: ContextVar[sqlite3.Connection | None] = ContextVar(
    "bankguard_transfer_connection", default=None,
)


@contextmanager
def transfer_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Use the caller's open write transaction for transfers and their audit rows."""
    if not conn.in_transaction or _transfer_connection.get() is not None:
        raise RuntimeError("Transfer requires one active caller transaction.")
    token = _transfer_connection.set(conn)
    try:
        yield
    finally:
        _transfer_connection.reset(token)


def execute_transfer(from_account_id: int, to_account_ref: str, amount: float) -> ToolResult:
    """Move PKR from a raw account id to a recipient reference, no auth.

    A numeric account id or exact account_number that exists in the local SQLite
    DB is credited in the same transaction. Other references are treated as
    external destinations: the source is debited, but no local credit is posted.
    """
    args = {
        "from_account_id": from_account_id,
        "to_account_ref": to_account_ref,
        "amount": amount,
    }
    conn = _transfer_connection.get()
    if conn is not None:
        return _run_transfer(conn, args)
    with closing(db.get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        return _run_transfer(conn, args)


def _run_transfer(conn: sqlite3.Connection, args: dict) -> ToolResult:
    result = _apply_transfer(conn, **args)
    _insert_tool_call(conn, "create_transfer", args, result.ok)
    return result


def _internal_recipient_id(conn: sqlite3.Connection, to_account_ref: str) -> int | None:
    """Resolve a recipient ref to a local account id, or None for external refs."""
    text = to_account_ref.strip()
    if text.isdecimal() and str(int(text)) == text:
        row = conn.execute(
            "SELECT id FROM accounts WHERE id = ?", (int(text),)
        ).fetchone()
        if row is not None:
            return row["id"]
    row = conn.execute(
        "SELECT id FROM accounts WHERE lower(account_number) = lower(?)", (text,)
    ).fetchone()
    return row["id"] if row is not None else None


def _apply_transfer(
    conn: sqlite3.Connection, from_account_id: int, to_account_ref: str, amount: float,
) -> ToolResult:
    if amount <= 0 or round(amount, 2) != amount:
        return ToolResult(ok=False, data={}, error="Amount must be positive with at most 2 decimals")
    account = conn.execute(
        "SELECT balance FROM accounts WHERE id = ?", (from_account_id,)
    ).fetchone()
    if account is None:
        return ToolResult(ok=False, data={}, error="Source account not found")
    if account["balance"] < amount:
        return ToolResult(ok=False, data={}, error="Insufficient funds")

    new_balance = round(account["balance"] - amount, 2)
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, from_account_id))
    conn.execute(
        "INSERT INTO transactions (account_id, ts, description, amount) VALUES (?, ?, ?, ?)",
        (from_account_id, ts, f"Transfer to {to_account_ref}", -amount),
    )

    destination_id = _internal_recipient_id(conn, to_account_ref)
    if destination_id is not None and destination_id != from_account_id:
        destination = conn.execute(
            "SELECT balance FROM accounts WHERE id = ?", (destination_id,)
        ).fetchone()
        if destination is None:
            return ToolResult(ok=False, data={}, error="Destination account not found")
        destination_balance = round(destination["balance"] + amount, 2)
        conn.execute(
            "UPDATE accounts SET balance = ? WHERE id = ?", (destination_balance, destination_id)
        )
        conn.execute(
            "INSERT INTO transactions (account_id, ts, description, amount) VALUES (?, ?, ?, ?)",
            (destination_id, ts, f"Transfer from {from_account_id}", amount),
        )

    return ToolResult(
        ok=True,
        data={
            "from_account_id": from_account_id,
            "to_account_ref": to_account_ref,
            "amount": amount,
            "new_balance": new_balance,
        },
        error=None,
    )
