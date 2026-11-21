"""Agent scaffolding. Owner: Ibraheem.

The offline `mock` provider gives a deterministic reply for dev and tests.
TODO(ibraheem): replace the canned output with a real LangChain agent wired to
`tool_executor`, at settings.llm_temperature (fixed at 0 by CONTRACT.md).
"""
from __future__ import annotations

from typing import Callable

from .config import settings
from .models import AgentOutput, Doc, ToolCall, ToolResult, User


def run_agent(
    user: User,
    message: str,
    history: list[dict],
    tool_executor: Callable[[ToolCall], ToolResult],
    docs: list[Doc],
) -> AgentOutput:
    """Return a canned AgentOutput; no real LLM or tool calls yet."""
    if settings.llm_provider == "mock":
        reply = f"[mock:{settings.llm_model}] BankGuard skeleton reply."
    else:
        # TODO(ibraheem): call the configured provider at temperature 0.
        reply = "[skeleton] BankGuard reply; real LLM not wired yet."
    return AgentOutput(reply=reply, tool_calls=[])
