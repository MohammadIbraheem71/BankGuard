"""Streamlit chat UI for BankGuard. Owner: Anum.

Talks to the FastAPI backend over HTTP only (httpx); it imports nothing from app/.

Run the backend, then the UI:
    uvicorn app.main:app --port 8000
    streamlit run ui/streamlit_app.py

BANKGUARD_API_URL overrides the backend address (default http://127.0.0.1:8000).
Demo logins are synthetic: alice / alice123 and bob / bob123.
"""
from __future__ import annotations

import os
import uuid

import httpx
import streamlit as st

API_URL = os.getenv("BANKGUARD_API_URL", "http://127.0.0.1:8000").rstrip("/")
REQUEST_TIMEOUT = 60.0
MODES = ("baseline", "detector_only", "full")
MODE_HELP = {
    "baseline": "LLM plus tools, no security checks (intentionally vulnerable).",
    "detector_only": "Inspects the user message only; blocks flagged messages.",
    "full": "Detector on messages and documents, policy on every tool call, "
            "transfer confirmation, response guard and event logging.",
}


def call(method: str, path: str, *, json: dict | None = None,
         params: dict | None = None) -> tuple[object | None, str | None]:
    """Call the backend. Returns (parsed JSON, None) or (None, user-facing error)."""
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


def init_state() -> None:
    """Create every session key the page relies on."""
    defaults = {
        "token": None,
        "username": None,
        "messages": [],
        "pending": None,        # PendingTransfer dict awaiting Confirm/Cancel
        "session_id": uuid.uuid4().hex,
        "mode": "full",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def log_in(username: str, password: str) -> None:
    """POST /login, then GET /me to show the signed-in customer."""
    data, error = call("POST", "/login", json={"username": username, "password": password})
    if error:
        st.error(error)
        return
    st.session_state.token = data["token"]
    me, error = call("GET", "/me")
    if error:
        st.session_state.token = None
        st.error(error)
        return
    st.session_state.username = me["username"]
    st.rerun()


def log_out() -> None:
    """Forget the token and every conversation-level value."""
    for key in ("token", "username", "pending"):
        st.session_state[key] = None
    st.session_state.messages = []
    st.session_state.session_id = uuid.uuid4().hex


def render_login() -> None:
    """Login page shown until a token is held."""
    st.title("BankGuard")
    st.caption("Security gateway for a synthetic banking chatbot. All data is fictional.")
    with st.form("login_form"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        log_in(username.strip(), password)


def render_sidebar() -> None:
    """Signed-in user, mode selector and session controls."""
    with st.sidebar:
        st.markdown(f"**Signed in as:** `{st.session_state.username}`")
        st.selectbox("Mode", MODES, key="mode", help="Gateway configuration for each message.")
        st.caption(MODE_HELP[st.session_state.mode])
        st.divider()
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = uuid.uuid4().hex
            st.session_state.pending = None
            st.rerun()
        if st.button("Log out", use_container_width=True):
            log_out()
            st.rerun()
        st.divider()
        st.caption(f"API: {API_URL}")


def _blocked_banner(detection: dict | None) -> None:
    """A red, unmissable banner for a blocked message or reply."""
    categories = ", ".join((detection or {}).get("categories", [])) or "security policy"
    reasons = "; ".join((detection or {}).get("reasons", []))
    text = f"**BLOCKED by BankGuard.** Reason: {categories}."
    if reasons:
        text += f" Details: {reasons}"
    st.error(text, icon="🚫")


def send_message(prompt: str) -> None:
    """Send one chat turn in the selected mode and record the response."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    data, error = call(
        "POST", "/chat",
        params={"mode": st.session_state.mode},
        json={"message": prompt, "session_id": st.session_state.session_id},
    )
    if error:
        st.session_state.messages.append({"role": "assistant", "content": error, "error": True})
        return

    pending = data.get("pending_transfer")
    if pending and pending.get("status") == "pending":
        st.session_state.pending = pending
    st.session_state.messages.append({
        "role": "assistant",
        "content": data["reply"],
        "blocked": data["blocked"],
        "detection": data.get("detection"),
        "tools": data.get("executed_tools", []),
        "latency_ms": data.get("latency_ms"),
        "mode": st.session_state.mode,
    })


def resolve_pending(action: str) -> None:
    """Confirm or cancel the pending transfer through the backend endpoint."""
    pending = st.session_state.pending
    if not pending:
        return
    result, error = call("POST", f"/transfers/{pending['id']}/{action}")
    st.session_state.pending = None
    if error:
        text = f"Transfer {action} failed: {error}"
    elif result["ok"]:
        verb = "confirmed" if action == "confirm" else "cancelled"
        text = (f"Transfer {verb}: PKR {pending['amount']:.2f} to "
                f"{pending['to_account_ref']} from account {pending['from_account_id']}.")
    else:
        text = f"Transfer {action} was not completed: {result.get('error') or 'unknown error'}"
    st.session_state.messages.append({"role": "assistant", "content": text, "error": not bool(result and result.get("ok"))})


def render_pending_card() -> None:
    """Show the exact recipient and amount, with Confirm and Cancel."""
    pending = st.session_state.pending
    if not pending:
        return
    with st.container(border=True):
        st.subheader("Transfer awaiting your confirmation")
        st.markdown(f"**From account:** {pending['from_account_id']}")
        st.markdown(f"**Recipient:** `{pending['to_account_ref']}`")
        st.markdown(f"**Amount:** PKR {pending['amount']:.2f}")
        st.caption(f"Pending transfer ID: {pending['id']}. Nothing moves until you confirm.")
        col_confirm, col_cancel = st.columns(2)
        col_confirm.button("Confirm transfer", type="primary", use_container_width=True,
                           key=f"confirm-{pending['id']}",
                           on_click=resolve_pending, args=("confirm",))
        col_cancel.button("Cancel", use_container_width=True,
                          key=f"cancel-{pending['id']}",
                          on_click=resolve_pending, args=("cancel",))


def render_messages() -> None:
    """Replay the conversation, with a banner on every blocked message."""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("blocked"):
                _blocked_banner(message.get("detection"))
            if message.get("error"):
                st.error(message["content"])
            else:
                st.markdown(message["content"])
            if message["role"] == "assistant" and not message.get("error"):
                tools = message.get("tools") or []
                summary = ", ".join(f"{t['name']} {t['args']}" for t in tools) or "no tools run"
                latency = message.get("latency_ms")
                suffix = f" · {latency:.0f} ms" if latency is not None else ""
                st.caption(f"Mode: {message.get('mode')} · {summary}{suffix}")


def main() -> None:
    """Page entry point."""
    st.set_page_config(page_title="BankGuard", page_icon="🏦", layout="centered")
    init_state()
    if not st.session_state.token:
        render_login()
        return

    render_sidebar()
    st.title("BankGuard chat")
    prompt = st.chat_input("Ask about balances, transactions, transfers or bank FAQs")
    if prompt:
        send_message(prompt.strip())
    render_pending_card()
    render_messages()


main()
