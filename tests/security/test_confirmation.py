import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from threading import Barrier

import pytest

from app import bank_api, db
from app.models import ToolCall
from app.security import confirmation

pytestmark = pytest.mark.usefixtures("seeded_bank")


@pytest.fixture
def transfer_call():
    return ToolCall(
        name="create_transfer",
        args={"from_account_id": 1001, "to_account_ref": "EXT-001", "amount": 125.50},
    )


@pytest.fixture
def pending(alice, transfer_call):
    return confirmation.create_pending(alice, transfer_call)


@pytest.fixture
def transactional_backend():
    if not hasattr(bank_api, "transfer_transaction"):
        pytest.skip("Requires the backend owner's transfer transaction patch")


def _read_state(pending_id):
    with closing(db.get_conn()) as conn:
        row = conn.execute(
            "SELECT * FROM pending_transfers WHERE id = ?", (pending_id,)
        ).fetchone()
        balance = conn.execute("SELECT balance FROM accounts WHERE id = 1001").fetchone()[0]
        debits = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE account_id = 1001 AND description LIKE 'Transfer to %'"
        ).fetchone()[0]
        audit = conn.execute(
            "SELECT user_id, ok FROM audit_log WHERE tool_name = 'create_transfer' ORDER BY id"
        ).fetchall()
    return row, balance, debits, [tuple(entry) for entry in audit]


def test_create_pending_has_five_minute_expiry_and_no_debit(pending, alice, transfer_call):
    row, balance, debits, audit = _read_state(pending.id)
    assert re.fullmatch(r"[A-Za-z0-9_-]{32}", pending.id)
    assert confirmation.create_pending(alice, transfer_call).id != pending.id
    assert row["status"] == "pending"
    assert row["binding_hash"].startswith("v2:")
    assert datetime.fromisoformat(row["expires_at"]) - datetime.fromisoformat(row["created_at"]) == timedelta(minutes=5)
    assert (balance, debits, audit) == (125_000, 0, [])


@pytest.mark.parametrize("call", [
    ToolCall(name="get_balance", args={"account_id": 1001}),
    ToolCall(name="create_transfer", args={"from_account_id": 2001, "to_account_ref": "EXT-01", "amount": 1}),
    ToolCall(name="create_transfer", args={"from_account_id": 1001, "to_account_ref": "EXT-01", "amount": 1.001}),
])
def test_create_pending_rejects_ineligible_calls(alice, call):
    with pytest.raises(ValueError, match="authorized transfer"):
        confirmation.create_pending(alice, call)
    with closing(db.get_conn()) as conn:
        assert conn.execute("SELECT count(*) FROM pending_transfers").fetchone()[0] == 0


def test_other_user_cannot_confirm_or_cancel(pending, bob):
    assert not confirmation.confirm(bob, pending.id).ok
    assert not confirmation.cancel(bob, pending.id).ok
    row, balance, debits, audit = _read_state(pending.id)
    assert row["status"] == "pending"
    assert (balance, debits, audit) == (125_000, 0, [])


def test_owner_can_cancel_only_once(pending, alice):
    assert confirmation.cancel(alice, pending.id).ok
    assert not confirmation.cancel(alice, pending.id).ok
    assert not confirmation.confirm(alice, pending.id).ok
    row, balance, debits, audit = _read_state(pending.id)
    assert row["status"] == "cancelled"
    assert (balance, debits, audit) == (125_000, 0, [])


def test_expiry_at_five_minute_boundary(pending, alice, monkeypatch):
    expiry = datetime.fromisoformat(pending.created_at) + timedelta(minutes=5)
    monkeypatch.setattr(confirmation, "_now", lambda: expiry)
    assert confirmation.confirm(alice, pending.id).error == "Pending transfer has expired."
    row, balance, debits, audit = _read_state(pending.id)
    assert row["status"] == "expired"
    assert (balance, debits, audit) == (125_000, 0, [])


@pytest.mark.parametrize(("field", "value"), [
    ("binding_hash", "v2:" + "0" * 64),
    ("amount", 130.25),
    ("from_account_id", 1002),
    ("to_account_ref", "EXT-002"),
    ("expires_at", "2099-01-01T00:00:00Z"),
    ("created_at", "2026-01-01T00:00:00Z"),
    ("id", "replacement-id"),
])
def test_tampering_is_rejected(pending, alice, field, value):
    with closing(db.get_conn()) as conn, conn:
        conn.execute(f"UPDATE pending_transfers SET {field} = ? WHERE id = ?", (value, pending.id))
    pending_id = value if field == "id" else pending.id
    assert confirmation.confirm(alice, pending_id).error == "Pending transfer failed its integrity check."
    _, balance, debits, audit = _read_state(pending_id)
    assert (balance, debits, audit) == (125_000, 0, [])


def test_legacy_pending_must_be_recreated(pending, alice):
    with closing(db.get_conn()) as conn, conn:
        conn.execute("UPDATE pending_transfers SET binding_hash = ? WHERE id = ?", ("0" * 64, pending.id))
    assert confirmation.confirm(alice, pending.id).error == "Please create a new transfer request."
    row, _, debits, audit = _read_state(pending.id)
    assert row["status"] == "cancelled"
    assert (debits, audit) == (0, [])


def test_missing_transaction_hook_prevents_debit(pending, alice, monkeypatch):
    monkeypatch.delattr(bank_api, "transfer_transaction", raising=False)
    assert confirmation.confirm(alice, pending.id).error == "Transfer confirmation is temporarily unavailable."
    row, balance, debits, audit = _read_state(pending.id)
    assert row["status"] == "pending"
    assert (balance, debits, audit) == (125_000, 0, [])


@pytest.mark.usefixtures("transactional_backend")
def test_one_confirmation_and_one_debit_through_http(alice):
    from fastapi.testclient import TestClient

    from app.auth import create_token
    from app.main import app

    headers = {"Authorization": f"Bearer {create_token(alice)}"}
    with TestClient(app) as client:
        response = client.post(
            "/chat?mode=full", headers=headers,
            json={"message": "Transfer 500 to account 2001", "session_id": "test-transfer"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["executed_tools"] == []
        pending_id = body["pending_transfer"]["id"]
        assert _read_state(pending_id)[1:] == (125_000, 0, [])
        chat_confirmation = client.post(
            "/chat?mode=full", headers=headers,
            json={"message": "Please confirm the pending transfer.", "session_id": "test-transfer"},
        )
        assert chat_confirmation.status_code == 200
        assert _read_state(pending_id)[0]["status"] == "pending"
        assert _read_state(pending_id)[1:] == (125_000, 0, [])

        endpoint = f"/transfers/{pending_id}/confirm"
        assert client.post(endpoint).status_code == 401
        barrier = Barrier(2, timeout=5)

        def send_confirmation(_):
            barrier.wait()
            reply = client.post(endpoint, headers=headers)
            assert reply.status_code == 200
            return reply.json()["ok"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(send_confirmation, range(2))) == [False, True]

        assert not client.post(endpoint, headers=headers).json()["ok"]
    row, balance, debits, audit = _read_state(pending_id)
    assert row["status"] == "confirmed"
    assert (balance, debits, audit) == (124_500, 1, [(alice.id, 1)])


@pytest.mark.usefixtures("transactional_backend")
def test_insufficient_funds_closes_pending_after_one_failed_audit(pending, alice):
    with closing(db.get_conn()) as conn, conn:
        conn.execute("UPDATE accounts SET balance = 100 WHERE id = 1001")
    assert confirmation.confirm(alice, pending.id).error == "Insufficient funds"
    assert not confirmation.confirm(alice, pending.id).ok
    row, balance, debits, audit = _read_state(pending.id)
    assert row["status"] == "cancelled"
    assert (balance, debits, audit) == (100, 0, [(alice.id, 0)])


@pytest.mark.usefixtures("transactional_backend")
@pytest.mark.parametrize("write_operation", ["INSERT ON audit_log", "UPDATE ON pending_transfers"])
def test_failure_rolls_back_debit_audit_and_status(pending, alice, write_operation):
    with closing(db.get_conn()) as conn, conn:
        conn.execute(
            f"CREATE TRIGGER simulated_failure BEFORE {write_operation} "
            "BEGIN SELECT RAISE(ABORT, 'Simulated database failure'); END"
        )

    with pytest.raises(sqlite3.IntegrityError, match="Simulated database failure"):
        confirmation.confirm(alice, pending.id)
    with closing(db.get_conn()) as conn, conn:
        conn.execute("DROP TRIGGER simulated_failure")

    row, balance, debits, audit = _read_state(pending.id)
    assert row["status"] == "pending"
    assert (balance, debits, audit) == (125_000, 0, [])
    assert confirmation.confirm(alice, pending.id).ok
    assert _read_state(pending.id)[1:] == (124_874.50, 1, [(alice.id, 1)])


@pytest.mark.usefixtures("transactional_backend")
def test_cancel_and_confirm_race_has_one_final_outcome(pending, alice):
    barrier = Barrier(2, timeout=5)

    def update(action):
        barrier.wait()
        return action(alice, pending.id).ok

    with ThreadPoolExecutor(max_workers=2) as executor:
        confirmed, cancelled = executor.map(update, [confirmation.confirm, confirmation.cancel])
    assert confirmed != cancelled

    row, balance, debits, audit = _read_state(pending.id)
    if confirmed:
        assert row["status"] == "confirmed"
        assert (balance, debits, audit) == (124_874.50, 1, [(alice.id, 1)])
    else:
        assert row["status"] == "cancelled"
        assert (balance, debits, audit) == (125_000, 0, [])
