"""Shared HTTP helpers for the BankGuard Streamlit pages. Owner: Anum.

Both ui/streamlit_app.py and ui/dashboard.py talk to the FastAPI backend only
through this module. It imports nothing from app/.
"""
from __future__ import annotations

import os

import httpx
import streamlit as st

API_URL = os.getenv("BANKGUARD_API_URL", "http://127.0.0.1:8000").rstrip("/")
REQUEST_TIMEOUT = 60.0


def call(method: str, path: str, *, json: dict | None = None,
         params: dict | None = None) -> tuple[object | None, str | None]:
    """Call the backend with the session's bearer token.

    Returns (parsed JSON, None) on success or (None, user-facing error message).
    A 401 on an authenticated call clears the stored token so the page shows login.
    """
    headers = {}
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = httpx.request(method, f"{API_URL}{path}", headers=headers,
                                 json=json, params=params, timeout=REQUEST_TIMEOUT)
    except httpx.HTTPError as exc:
        return None, f"Cannot reach the BankGuard API at {API_URL} ({exc.__class__.__name__})."

    if response.status_code == 401 and token:
        st.session_state.token = None
        return None, "Your session has expired. Please log in again."
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        return None, f"Request failed ({response.status_code}): {detail}"
    return response.json(), None


def log_in(username: str, password: str) -> str | None:
    """POST /login then GET /me. Stores the token and username; returns an error or None."""
    data, error = call("POST", "/login", json={"username": username, "password": password})
    if error:
        return error
    st.session_state.token = data["token"]
    me, error = call("GET", "/me")
    if error:
        st.session_state.token = None
        return error
    st.session_state.username = me["username"]
    return None
