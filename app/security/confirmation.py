"""Transfer confirmation flow. Owner: Muzammil.

TODO(muzammil): harden binding_hash with session context and add expiry sweeps.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from app import bank_api, db
from app.config import settings
from app.models import PendingTransfer, ToolCall, ToolResult, User

_PENDING_TTL_MINUTES = 10


def _binding_hash(user_id: int, from_account_id: int, to_account_ref: str, amount: float) -> str:
    """Sign the transfer details so a pending id cannot be replayed with edits."""
    message = f"{user_id}|{from_account_id}|{to_account_ref}|{round(amount, 2)}"
    return hmac.new(settings.secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def create_pending(user: User, call: ToolCall) -> PendingTransfer:
    """Create and persist a plausible pending transfer for the user to confirm."""
    # TODO(muzammil): replace this permissive placeholder with strict validation.
    from_account_id = int(call.args["from_account_id"])
    to_account_ref = str(call.args["to_account_ref"])
    amount = round(float(call.args["amount"]), 2)
    now = datetime.now(timezone.utc)
    pending = PendingTransfer(
        id=uuid.uuid4().hex,
        user_id=user.id,
        from_account_id=from_account_id,
        to_account_ref=to_account_ref,
        amount=amount,
        status="pending",
        created_at=now.isoformat().replace("+00:00", "Z"),
    )
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO pending_transfers "
            "(id, user_id, from_account_id, to_account_ref, amount, binding_hash, status, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (
                pending.id,
                user.id,
                from_account_id,
                to_account_ref,
                amount,
                _binding_hash(user.id, from_account_id, to_account_ref, amount),
                pending.created_at,
                (now + timedelta(minutes=_PENDING_TTL_MINUTES)).isoformat().replace("+00:00", "Z"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return pending


def confirm(user: User, pending_id: str) -> ToolResult:
    """Confirm a pending transfer and execute it if the binding still matches."""
    # TODO(muzammil): expand checks (expiry, session binding, audit events).
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM pending_transfers WHERE id = ?", (pending_id,)).fetchone()
        if row is None:
            return ToolResult(ok=False, data={}, error="Pending transfer not found")
        if row["user_id"] != user.id or row["status"] != "pending":
            return ToolResult(ok=False, data={}, error="Pending transfer is not confirmable by this user")
        expected = _binding_hash(
            row["user_id"], row["from_account_id"], row["to_account_ref"], row["amount"]
        )
        if not hmac.compare_digest(row["binding_hash"], expected):
            return ToolResult(ok=False, data={}, error="Binding check failed")
        result = bank_api.execute_transfer(
            row["from_account_id"], row["to_account_ref"], row["amount"]
        )
        if result.ok:
            conn.execute(
                "UPDATE pending_transfers SET status = 'confirmed' WHERE id = ?", (pending_id,)
            )
            conn.commit()
        return ToolResult(ok=result.ok, data={"pending_id": pending_id, **result.data}, error=result.error)
    finally:
        conn.close()


def cancel(user: User, pending_id: str) -> ToolResult:
    """Cancel a pending transfer owned by `user`."""
    # TODO(muzammil): log the cancellation as a security event.
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT user_id, status FROM pending_transfers WHERE id = ?", (pending_id,)).fetchone()
        if row is None or row["user_id"] != user.id:
            return ToolResult(ok=False, data={}, error="Pending transfer not found for this user")
        if row["status"] != "pending":
            return ToolResult(ok=False, data={}, error="Pending transfer is no longer pending")
        conn.execute("UPDATE pending_transfers SET status = 'cancelled' WHERE id = ?", (pending_id,))
        conn.commit()
        return ToolResult(ok=True, data={"pending_id": pending_id, "status": "cancelled"}, error=None)
    finally:
        conn.close()
