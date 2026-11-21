"""THE pipeline. Owner: Ibraheem.

Every UI, API and eval chat goes through handle_message. Security steps are
marked below with PLUG-IN comments so owners can drop their implementations in
without changing this signature or the mode semantics from CONTRACT.md.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from . import bank_api, chatbot, db, retrieval
from .config import Mode
from .models import (
    ChatRequest,
    ChatResponse,
    DetectionResult,
    Doc,
    PendingTransfer,
    ToolCall,
    ToolResult,
    User,
)
from .security import confirmation, detector, events, policy, response_guard


def _mode_name(mode: Mode) -> str:
    """Normalize a Mode enum (or a raw string from a caller) to a log string."""
    return mode.value if isinstance(mode, Mode) else str(mode)


def _now() -> str:
    """UTC ISO-8601 timestamp for audit rows."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _audit(user_id: int, mode: str, call: ToolCall, result: ToolResult) -> None:
    """Record every EXECUTED tool call; this table is eval ground truth."""
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO audit_log (ts, user_id, mode, tool_name, args_json, ok) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), user_id, mode, call.name, json.dumps(call.args, sort_keys=True), int(result.ok)),
        )
        conn.commit()
    finally:
        conn.close()


def _dispatch(call: ToolCall) -> ToolResult:
    """Execute a tool against the raw bank/retrieval APIs, without auth."""
    try:
        if call.name == "get_balance":
            return bank_api.get_balance(int(call.args["account_id"]))
        if call.name == "get_transactions":
            return bank_api.get_transactions(
                int(call.args["account_id"]), int(call.args.get("limit", 10))
            )
        if call.name == "create_transfer":
            return bank_api.execute_transfer(
                int(call.args["from_account_id"]),
                str(call.args["to_account_ref"]),
                float(call.args["amount"]),
            )
        if call.name == "search_faq":
            docs = retrieval.search(str(call.args["query"]))
            return ToolResult(ok=True, data={"docs": [d.model_dump() for d in docs]}, error=None)
    except (KeyError, TypeError, ValueError) as exc:
        return ToolResult(ok=False, data={}, error=f"Invalid tool arguments: {exc}")
    return ToolResult(ok=False, data={}, error="Unknown tool")


def handle_message(user: User, req: ChatRequest, mode: Mode) -> ChatResponse:
    """Run one chat turn in the selected mode and return the only chat type."""
    started = time.perf_counter()
    mode_name = _mode_name(mode)
    detection: DetectionResult | None = None
    pending_transfer: PendingTransfer | None = None
    executed_tools: list[ToolCall] = []
    blocked = False
    reply = "Blocked by BankGuard security policy."
    docs: list[Doc] = []

    # STEP 1 — DOCUMENT RETRIEVAL (full only; placeholder returns []).
    if mode == Mode.full:
        docs = retrieval.search(req.message)

    # STEP 2 — USER-MESSAGE INSPECTION (detector_only and full).
    if mode in (Mode.detector_only, Mode.full):
        # >>> PLUG-IN POINT: Muzammil's detector.inspect(..., source="user") <<<
        detection = detector.inspect(req.message, source="user")
        if detection.flagged:
            if mode == Mode.full:
                # >>> PLUG-IN POINT: event logging for blocked user messages <<<
                events.log_event(
                    user.id, mode_name, "blocked_user_message", "high",
                    "Blocked: user message flagged", {"categories": detection.categories},
                )
            return ChatResponse(
                reply=reply, blocked=True, pending_transfer=None, executed_tools=[],
                detection=detection, latency_ms=(time.perf_counter() - started) * 1000,
            )

    # STEP 3 — DOCUMENT INSPECTION (full only).
    if mode == Mode.full:
        for doc in docs:
            # >>> PLUG-IN POINT: Muzammil's detector.inspect(..., source="document") <<<
            doc_detection = detector.inspect(doc.text, source="document")
            if doc_detection.flagged:
                detection = doc_detection
                blocked = True
                # >>> PLUG-IN POINT: event logging for poisoned documents <<<
                events.log_event(
                    user.id, mode_name, "blocked_document", "high",
                    "Blocked: retrieved document flagged", {"doc_id": doc.id},
                )
                break
        if blocked:
            return ChatResponse(
                reply=reply, blocked=True, pending_transfer=None, executed_tools=[],
                detection=detection, latency_ms=(time.perf_counter() - started) * 1000,
            )

    # STEP 4 — TOOL EXECUTION HOOK, handed to the agent.
    def tool_executor(call: ToolCall) -> ToolResult:
        nonlocal pending_transfer

        # STEP 4a — POLICY ON EVERY TOOL CALL (full only).
        if mode == Mode.full:
            # >>> PLUG-IN POINT: Muzammil's policy.authorize(user, call) <<<
            decision = policy.authorize(user, call)
            if not decision.allowed:
                events.log_event(
                    user.id, mode_name, "policy_denied", "high",
                    "Denied: tool call rejected by policy", {"tool": call.name},
                )
                return ToolResult(ok=False, data={}, error=f"Policy denied: {decision.reason}")

            # STEP 4b — CONFIRMATION FOR TRANSFERS (full only).
            if decision.requires_confirmation and call.name == "create_transfer":
                # >>> PLUG-IN POINT: Muzammil's confirmation.create_pending(...) <<<
                pending_transfer = confirmation.create_pending(user, call)
                events.log_event(
                    user.id, mode_name, "transfer_pending", "medium",
                    "Pending transfer awaits user confirmation", {"id": pending_transfer.id},
                )
                return ToolResult(
                    ok=False,
                    data={"pending_transfer_id": pending_transfer.id},
                    error="Confirmation required",
                )

        # STEP 5 — EXECUTE AND AUDIT (all three modes).
        result = _dispatch(call)
        executed_tools.append(call)
        _audit(user.id, mode_name, call, result)
        return result

    # STEP 6 — AGENT / MOCK LLM (same call in all modes).
    output = chatbot.run_agent(user, req.message, [], tool_executor, docs)
    reply = output.reply

    # STEP 7 — RESPONSE GUARD (full only).
    if mode == Mode.full:
        # >>> PLUG-IN POINT: Muzammil's response_guard.check(...) <<<
        guard = response_guard.check(user, reply, verified_facts={})
        reply = guard.text
        if not guard.safe:
            blocked = True
            events.log_event(
                user.id, mode_name, "response_guard_blocked", "high",
                "Blocked: outbound reply marked unsafe", {"findings": guard.findings},
            )

    # STEP 8 — EVENT LOGGING (full only).
    if mode == Mode.full:
        # >>> PLUG-IN POINT: Muzammil's events.log_event(...) <<<
        events.log_event(
            user.id, mode_name, "chat_completed", "low", "Chat handled in full mode",
            {"blocked": blocked, "tools": [c.name for c in executed_tools]},
        )

    return ChatResponse(
        reply=reply,
        blocked=blocked,
        pending_transfer=pending_transfer,
        executed_tools=executed_tools,
        detection=detection,
        latency_ms=(time.perf_counter() - started) * 1000,
    )
