"""Password hashing and stateless bearer tokens. Owner: Ibraheem.

Tokens are intentionally stateless for this demo: there is no revocation list,
rotation endpoint, or server-side logout. See docs/architecture.md.
Hash format: pbkdf2_sha256$iterations$salt_hex$hash_hex.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Annotated

from fastapi import Header, HTTPException, status

from . import db
from .config import settings
from .models import User

PBKDF2_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 3600


def hash_password(password: str) -> str:
    """Hash a synthetic demo password with a fresh per-user salt."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of a password against a stored PBKDF2 hash."""
    try:
        algorithm, iterations, salt_hex, expected_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def create_token(user: User) -> str:
    """Create an HMAC-SHA256 signed, expiring bearer token for `user`."""
    payload = {"sub": str(user.id), "exp": time.time() + TOKEN_TTL_SECONDS}
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(settings.secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def decode_token(token: str) -> int | None:
    """Return the user id from a valid token, or None if it is bad/expired."""
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            settings.secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if float(payload["exp"]) < time.time():
            return None
        return int(payload["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _user_by_id(user_id: int) -> User | None:
    """Load a User (including account ids) from the database."""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        accounts = conn.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,)).fetchall()
        return User(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            account_ids=[a["id"] for a in accounts],
        )
    finally:
        conn.close()


def authenticate(username: str, password: str) -> User | None:
    """Return the matching synthetic user, or None for bad credentials."""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return _user_by_id(row["id"])


def get_current_user(authorization: Annotated[str | None, Header()] = None) -> User:
    """FastAPI dependency that resolves a `Bearer` token to a User."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    user_id = decode_token(authorization.removeprefix("Bearer ").strip())
    user = _user_by_id(user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user
