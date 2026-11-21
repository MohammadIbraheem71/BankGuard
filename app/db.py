"""SQLite connection, schema and reset logic. Owner: Ibraheem.

The six tables below are exactly the tables defined in CONTRACT.md.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import BASE_DIR, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    cnic TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    account_number TEXT NOT NULL,
    type TEXT NOT NULL,
    balance REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    ts TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_transfers (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    from_account_id INTEGER NOT NULL,
    to_account_ref TEXT NOT NULL,
    amount REAL NOT NULL,
    binding_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user_id INTEGER,
    mode TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user_id INTEGER,
    mode TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    args_json TEXT NOT NULL,
    ok INTEGER NOT NULL
);
"""

TABLES = (
    "audit_log",
    "security_events",
    "pending_transfers",
    "transactions",
    "accounts",
    "users",
)


def _db_path() -> Path:
    """Resolve DB_PATH relative to the repository root when it is relative."""
    configured = Path(settings.db_path)
    return configured if configured.is_absolute() else BASE_DIR / configured


def get_conn() -> sqlite3.Connection:
    """Return a SQLite connection with row-factory and foreign keys enabled."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all contract tables if they do not already exist."""
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def reset_and_seed() -> None:
    """Fully wipe every table, recreate the schema and reseed synthetic data."""
    from .seed import seed_all  # local import: seed.py imports auth.py, which imports db.py

    conn = get_conn()
    try:
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.executescript(SCHEMA)
        conn.commit()
        seed_all(conn)
        conn.commit()
    finally:
        conn.close()
