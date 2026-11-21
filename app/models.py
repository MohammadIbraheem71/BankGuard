"""Shared pydantic v2 models, transcribed from CONTRACT.md. Owner: Ibraheem.

Do not rename or add required fields here without editing CONTRACT.md first.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class User(BaseModel):
    """Authenticated customer identity (all data is synthetic)."""

    id: int
    username: str
    role: Literal["customer"]
    account_ids: list[int]


ToolName = Literal["get_balance", "get_transactions", "create_transfer", "search_faq"]


class ToolCall(BaseModel):
    """A single tool invocation requested by the agent.

    get_balance{account_id:int} | get_transactions{account_id:int, limit:int=10}
    create_transfer{from_account_id:int, to_account_ref:str, amount:float (PKR, max 2 decimals)}
    search_faq{query:str}
    """

    name: ToolName
    args: dict


class ToolResult(BaseModel):
    """Return value of a tool; data is a plain dict for eval-friendly JSON."""

    ok: bool
    data: dict
    error: str | None


class Doc(BaseModel):
    """A retrieved document; trusted=false marks untrusted/poisoned content."""

    id: str
    title: str
    text: str
    trusted: bool


class DetectionResult(BaseModel):
    """Detector verdict. Categories are a subset of the five in CONTRACT.md."""

    flagged: bool
    score: float = Field(ge=0.0, le=1.0)
    categories: list[str]
    reasons: list[str]


class PolicyDecision(BaseModel):
    """Policy engine verdict for one tool call."""

    allowed: bool
    reason: str
    requires_confirmation: bool = False


class GuardResult(BaseModel):
    """Response-guard verdict; text is always the redacted output to show."""

    safe: bool
    text: str
    findings: list[str]


class PendingTransfer(BaseModel):
    """A transfer awaiting explicit user confirmation."""

    id: str
    user_id: int
    from_account_id: int
    to_account_ref: str
    amount: float
    status: Literal["pending", "confirmed", "cancelled", "expired"]
    created_at: str


class SecurityEvent(BaseModel):
    """A logged security event. summary is ALWAYS redacted."""

    ts: str
    user_id: int | None
    mode: str
    event_type: str
    severity: Literal["low", "medium", "high"]
    summary: str
    details: dict


class ChatRequest(BaseModel):
    """Inbound chat message plus the client-side conversation id."""

    message: str
    session_id: str


class ChatResponse(BaseModel):
    """The only chat return type used by UI, API and eval."""

    reply: str
    blocked: bool
    pending_transfer: PendingTransfer | None
    executed_tools: list[ToolCall]
    detection: DetectionResult | None
    latency_ms: float


class AgentOutput(BaseModel):
    """LLM/agent result: a reply and the tool calls it wants to make."""

    reply: str
    tool_calls: list[ToolCall]
