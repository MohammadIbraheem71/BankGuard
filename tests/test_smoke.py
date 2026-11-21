"""Walking-skeleton smoke tests. Owner: Ibraheem.

One mocked-LLM chat through the gateway in each mode, plus the canary-seed
invariant that the eval cases depend on.
"""
from __future__ import annotations

import pytest

from app.config import Mode, settings
from app.db import get_conn, reset_and_seed
from app.gateway import handle_message
from app.models import ChatRequest, ChatResponse, User


@pytest.fixture(scope="module", autouse=True)
def seeded_database() -> None:
    """Give every test in this module the same fully reseeded synthetic DB."""
    reset_and_seed()


@pytest.fixture(autouse=True)
def force_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests always use the deterministic offline 'mock' LLM."""
    monkeypatch.setattr(settings, "llm_provider", "mock")


def _alice() -> User:
    return User(id=1, username="alice", role="customer", account_ids=[1001, 1002])


@pytest.mark.parametrize("mode", list(Mode))
def test_chat_returns_chat_response_in_each_mode(mode: Mode) -> None:
    """All three modes return a ChatResponse from gateway.handle_message."""
    response = handle_message(
        _alice(),
        ChatRequest(message="What is my balance?", session_id=f"smoke-{mode.value}"),
        mode,
    )
    assert isinstance(response, ChatResponse)
    assert response.blocked is False
    assert response.reply.startswith("[mock:")
    assert response.latency_ms >= 0.0
    assert response.detection is None or response.detection.flagged is False


def test_canary_is_newest_transaction_on_primary_accounts() -> None:
    """Default get_transactions(limit=10) must expose each canary string."""
    conn = get_conn()
    try:
        expected = {1001: "Memo CANARY-ALICE-7731", 2001: "Memo CANARY-BOB-4482"}
        for account_id, description in expected.items():
            row = conn.execute(
                "SELECT description FROM transactions WHERE account_id = ? "
                "ORDER BY ts DESC, id DESC LIMIT 1",
                (account_id,),
            ).fetchone()
            assert row is not None
            assert row["description"] == description
    finally:
        conn.close()
