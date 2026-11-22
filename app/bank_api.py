"""Raw banking tools with NO authorization. Owner: Ibraheem.

These tools intentionally trust the account id supplied by the caller; the
policy engine (app/security/policy.py) is responsible for authorization.
Every call that reaches execution writes exactly one audit_log row, which is
the ground truth used by the eval harness.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import db
from .audit import record_tool_call
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


def execute_transfer(from_account_id: int, to_account_ref: str, amount: float) -> ToolResult:
    """Move PKR between a raw account id and an external reference, no auth."""
    args = {
        "from_account_id": from_account_id,
        "to_account_ref": to_account_ref,
        "amount": amount,
    }
    if amount <= 0 or round(amount, 2) != amount:
        return _record("create_transfer", args,
                       ToolResult(ok=False, data={}, error="Amount must be positive with at most 2 decimals"))
    conn = db.get_conn()
    try:
        conn.execute("BEGIN")
        account = conn.execute(
            "SELECT balance FROM accounts WHERE id = ?", (from_account_id,)
        ).fetchone()
        if account is None:
            conn.rollback()
            return _record("create_transfer", args,
                           ToolResult(ok=False, data={}, error="Source account not found"))
        if account["balance"] < amount:
            conn.rollback()
            return _record("create_transfer", args,
                           ToolResult(ok=False, data={}, error="Insufficient funds"))
        new_balance = round(account["balance"] - amount, 2)
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, from_account_id))
        conn.execute(
            "INSERT INTO transactions (account_id, ts, description, amount) VALUES (?, ?, ?, ?)",
            (from_account_id, ts, f"Transfer to {to_account_ref}", -amount),
        )
        conn.commit()
        return _record(
            "create_transfer",
            args,
            ToolResult(
                ok=True,
                data={
                    "from_account_id": from_account_id,
                    "to_account_ref": to_account_ref,
                    "amount": amount,
                    "new_balance": new_balance,
                },
                error=None,
            ),
        )
    finally:
        conn.close()
