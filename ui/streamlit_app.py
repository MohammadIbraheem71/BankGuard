"""Streamlit chat UI for BankGuard. Owner: Anum.

Talks to the FastAPI backend over HTTP only (httpx); it imports nothing from app/.

Run the backend, then the UI:
    uvicorn app.main:app --port 8000
    streamlit run ui/streamlit_app.py

BANKGUARD_API_URL overrides the backend address (default http://127.0.0.1:8000).
Demo logins are synthetic: alice / alice123 and bob / bob123.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

# Streamlit adds this script's folder to sys.path; keep it explicit for other runners.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import API_URL, call, log_in  # noqa: E402

MODES = ("baseline", "detector_only", "full")
MODE_HELP = {
    "baseline": "LLM plus tools, no security checks (intentionally vulnerable).",
    "detector_only": "Inspects the user message only; blocks flagged messages.",
    "full": "Detector on messages and documents, policy on every tool call, "
            "transfer confirmation, response guard and event logging.",
}


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


def _log_in_and_rerun(username: str, password: str) -> None:
    error = log_in(username, password)
    if error:
        st.error(error)
        return
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
        _log_in_and_rerun(username.strip(), password)


def render_sidebar() -> None:
    """Signed-in user, mode selector and session controls."""
    with st.sidebar:
        st.markdown(f"**Signed in as:** `{st.session_state.username}`")
        st.selectbox("Mode", MODES, key="mode", help="Gateway configuration for each message.")
        st.caption(MODE_HELP[st.session_state.mode])
        st.divider()
        if st.button("Clear conversation", width="stretch"):
            st.session_state.messages = []
            st.session_state.session_id = uuid.uuid4().hex
            st.session_state.pending = None
            st.rerun()
        if st.button("Log out", width="stretch"):
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
    st.session_state.messages.append({
        "role": "assistant",
        "content": text,
        "error": not bool(result and result.get("ok")),
        "mode": st.session_state.mode,
    })


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
        col_confirm.button("Confirm transfer", type="primary", width="stretch",
                           key=f"confirm-{pending['id']}",
                           on_click=resolve_pending, args=("confirm",))
        col_cancel.button("Cancel", width="stretch",
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
