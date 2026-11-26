"""Persist transfer requests and confirm them through one SQLite transaction."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app import bank_api, db
from app.config import settings
from app.models import PendingTransfer, ToolCall, ToolResult, User

from . import events, policy

_PENDING_TTL = timedelta(minutes=5)
_BINDING_VERSION = "v2:"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _binding_hash(
    pending_id: str,
    user_id: int,
    from_account_id: int,
    to_account_ref: str,
    amount: float,
    created_at: str,
    expires_at: str,
) -> str:
    fields = [pending_id, user_id, from_account_id, to_account_ref,
              int(Decimal(str(amount)) * 100), created_at, expires_at]
    message = json.dumps(fields, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    digest = hmac.new(settings.secret_key.encode("utf-8"), message, hashlib.sha256)
    return _BINDING_VERSION + digest.hexdigest()


def _failure(reason: str) -> ToolResult:
    return ToolResult(ok=False, data={}, error=reason)


def _set_status(conn, pending_id: str, status: str) -> None:
    conn.execute("UPDATE pending_transfers SET status = ? WHERE id = ?", (status, pending_id))


def create_pending(user: User, call: ToolCall) -> PendingTransfer:
    decision = policy.authorize(user, call)
    if not decision.allowed or not decision.requires_confirmation:
        raise ValueError("An authorized transfer is required.")

    issued = _now()
    expires_at = _timestamp(issued + _PENDING_TTL)
    pending = PendingTransfer(
        id=secrets.token_urlsafe(24),
        user_id=user.id,
        from_account_id=call.args["from_account_id"],
        to_account_ref=call.args["to_account_ref"],
        amount=call.args["amount"],
        status="pending",
        created_at=_timestamp(issued),
    )
    fields = (
        pending.id, pending.user_id, pending.from_account_id,
        pending.to_account_ref, pending.amount, pending.created_at, expires_at,
    )
    with closing(db.get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO pending_transfers "
            "(id, user_id, from_account_id, to_account_ref, amount, created_at, expires_at, binding_hash, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (*fields, _binding_hash(*fields)),
        )
    return pending


def confirm(user: User, pending_id: str) -> ToolResult:
    with closing(db.get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM pending_transfers WHERE id = ? AND user_id = ?",
            (pending_id, user.id),
        ).fetchone()
        if row is None or row["status"] != "pending":
            return _failure("Pending transfer is unavailable.")

        binding = row["binding_hash"]
        if not binding.startswith(_BINDING_VERSION):
            _set_status(conn, pending_id, "cancelled")
            return _failure("Please create a new transfer request.")

        args = {
            "from_account_id": row["from_account_id"],
            "to_account_ref": row["to_account_ref"],
            "amount": row["amount"],
        }
        decision = policy.authorize(user, ToolCall(name="create_transfer", args=args))
        if not decision.allowed or not decision.requires_confirmation:
            return _failure("Pending transfer is no longer authorized.")

        expected = _binding_hash(
            pending_id, user.id, args["from_account_id"], args["to_account_ref"],
            args["amount"], row["created_at"], row["expires_at"],
        )
        if not hmac.compare_digest(binding.encode("utf-8"), expected.encode("ascii")):
            return _failure("Pending transfer failed its integrity check.")
        if _now() >= datetime.fromisoformat(row["expires_at"]):
            _set_status(conn, pending_id, "expired")
            return _failure("Pending transfer has expired.")

        # The backend hook makes the bank tool and audit writer borrow this transaction.
        transaction = getattr(bank_api, "transfer_transaction", None)
        if transaction is None:
            return _failure("Transfer confirmation is temporarily unavailable.")
        with transaction(conn):
            result = bank_api.execute_transfer(**args)
        _set_status(conn, pending_id, "confirmed" if result.ok else "cancelled")
        return ToolResult(ok=result.ok, data={"pending_id": pending_id, **result.data}, error=result.error)


def cancel(user: User, pending_id: str) -> ToolResult:
    with closing(db.get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        updated = conn.execute(
            "UPDATE pending_transfers SET status = 'cancelled' "
            "WHERE id = ? AND user_id = ? AND status = 'pending'",
            (pending_id, user.id),
        )
        if updated.rowcount != 1:
            return _failure("Pending transfer is unavailable.")
        result = ToolResult(ok=True, data={"pending_id": pending_id, "status": "cancelled"}, error=None)
    events.log_event(user.id, "full", "transfer_cancelled", "low", "", {"pending_id": pending_id})
    return result
