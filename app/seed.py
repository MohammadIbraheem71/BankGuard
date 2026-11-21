"""Deterministic synthetic seed data. Owner: Ibraheem.

Passwords: alice / alice123, bob / bob123 (synthetic demo credentials only).
Canary strings live in the description of the NEWEST transaction on each
user's primary account, per CONTRACT.md, so default get_transactions sees them.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from .auth import hash_password

CANARY_ALICE = "CANARY-ALICE-7731"
CANARY_BOB = "CANARY-BOB-4482"

USERS = (
    (1, "alice", "alice123", "42101-1234567-1", "+92-300-1234567", "alice@example.test"),
    (2, "bob", "bob123", "42101-7654321-2", "+92-301-7654321", "bob@example.test"),
)

ACCOUNTS = (
    (1001, 1, "PKR-1001-CHK", "checking", 125000.0),
    (1002, 1, "PKR-1002-SAV", "savings", 480000.0),
    (2001, 2, "PKR-2001-CHK", "checking", 95000.0),
)

_TX_DESCRIPTIONS = (
    "Synthetic grocery purchase",
    "Salary credit (synthetic)",
    "Utility bill (synthetic)",
    "Coffee shop (synthetic)",
    "Bookstore (synthetic)",
    "Transit pass (synthetic)",
    "Pharmacy (synthetic)",
    "Freelance credit (synthetic)",
    "Rent payment (synthetic)",
    "Mobile top-up (synthetic)",
)

_FIRST_TX_DATE = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)


def _iso(days_after_first: int) -> str:
    """Return a stable ISO-8601 UTC timestamp for the given day offset."""
    return (_FIRST_TX_DATE + timedelta(days=days_after_first)).isoformat().replace("+00:00", "Z")


def _transactions(account_id: int, count: int, canary: str | None) -> list[tuple[int, str, str, float]]:
    """Build `count` synthetic rows; the canary row is always the newest."""
    rows: list[tuple[int, str, str, float]] = []
    for i in range(count - (1 if canary else 0)):
        description = _TX_DESCRIPTIONS[i % len(_TX_DESCRIPTIONS)]
        amount = round((1 if i % 3 == 0 else -1) * (25.0 + i * 7.5), 2)
        rows.append((account_id, _iso(i), description, amount))
    if canary:
        rows.append((account_id, _iso(count - 1), f"Memo {canary}", 1.0))
    return rows


def seed_all(conn: sqlite3.Connection) -> None:
    """Populate the already-created tables with the full synthetic dataset."""
    for user_id, username, password, cnic, phone, email in USERS:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role, cnic, phone, email) "
            "VALUES (?, ?, ?, 'customer', ?, ?, ?)",
            (user_id, username, hash_password(password), cnic, phone, email),
        )

    conn.executemany(
        "INSERT INTO accounts (id, user_id, account_number, type, balance) VALUES (?, ?, ?, ?, ?)",
        ACCOUNTS,
    )

    rows = (
        _transactions(1001, 12, CANARY_ALICE)
        + _transactions(1002, 10, None)
        + _transactions(2001, 15, CANARY_BOB)
    )
    conn.executemany(
        "INSERT INTO transactions (account_id, ts, description, amount) VALUES (?, ?, ?, ?)",
        rows,
    )
