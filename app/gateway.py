"""THE pipeline. Owner: Ibraheem.

Every UI, API and eval chat goes through handle_message. Security steps are
marked below with PLUG-IN comments so owners can drop their implementations in
without changing this signature or the mode semantics from CONTRACT.md.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict

from . import bank_api, chatbot, retrieval
from .audit import record_tool_call, tool_context
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


# Session memory is intentionally process-local: it is a demo/eval aid, not a
# durable chat store. One "turn" below is one completed user/assistant pair.
MAX_SESSION_TURNS = 10
MAX_SESSIONS = 1000
_SESSION_LOCK = threading.Lock()
_SESSIONS: "OrderedDict[tuple[int, str], list[list[dict]]]" = OrderedDict()


def clear_sessions() -> None:
    """Drop all in-memory conversation history (used by tests and reseeds)."""
    with _SESSION_LOCK:
        _SESSIONS.clear()


def _history_snapshot(key: tuple[int, str]) -> list[dict]:
    """Return a flat, detached copy of the session's most recent exchanges."""
    with _SESSION_LOCK:
        turns = _SESSIONS.get(key)
        if turns is None:
            return []
        _SESSIONS.move_to_end(key)
        history: list[dict] = []
        for pair in turns[-MAX_SESSION_TURNS:]:
            history.extend(dict(message) for message in pair)
        return history


def _remember_turn(key: tuple[int, str], message: str, reply: str) -> None:
    """Store one non-blocked exchange; evict the oldest session if full."""
    with _SESSION_LOCK:
        if key not in _SESSIONS:
            while len(_SESSIONS) >= MAX_SESSIONS:
                _SESSIONS.popitem(last=False)
        turns = _SESSIONS.setdefault(key, [])
        turns.append([
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply},
        ])
        if len(turns) > MAX_SESSION_TURNS:
            del turns[:-MAX_SESSION_TURNS]
        _SESSIONS.move_to_end(key)


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
            query = str(call.args["query"])
            docs = retrieval.search(query)
            result = ToolResult(ok=True, data={"docs": [d.model_dump() for d in docs]}, error=None)
            record_tool_call("search_faq", {"query": query}, result.ok)
            return result
    except (KeyError, TypeError, ValueError) as exc:
        return ToolResult(ok=False, data={}, error=f"Invalid tool arguments: {exc}")
    return ToolResult(ok=False, data={}, error="Unknown tool")


def handle_message(user: User, req: ChatRequest, mode: Mode) -> ChatResponse:
    """Run one chat turn in the selected mode and return the only chat type."""
    started = time.perf_counter()
    with tool_context(user.id, _mode_name(mode)):
        return _run_pipeline(user, req, mode, started)


def _run_pipeline(user: User, req: ChatRequest, mode: Mode, started: float) -> ChatResponse:
    """Mode-aware chat pipeline; called inside the request's audit context."""
    mode_name = _mode_name(mode)
    detection: DetectionResult | None = None
    pending_transfer: PendingTransfer | None = None
    executed_tools: list[ToolCall] = []
    verified_facts: dict[str, list[dict]] = {}
    blocked = False
    policy_denied = False
    reply = "Blocked by BankGuard security policy."
    docs: list[Doc] = []
    history_key = (user.id, req.session_id)
    history = _history_snapshot(history_key)

    # STEP 1 — DOCUMENT RETRIEVAL (all modes; RAG is part of the baseline).
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

    # STEP 3 — DOCUMENT INSPECTION (full only; flagged docs are dropped).
    if mode == Mode.full:
        kept_docs: list[Doc] = []
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
            else:
                kept_docs.append(doc)
        docs = kept_docs
        if blocked:
            return ChatResponse(
                reply=reply, blocked=True, pending_transfer=None, executed_tools=[],
                detection=detection, latency_ms=(time.perf_counter() - started) * 1000,
            )

    # STEP 4 — TOOL EXECUTION HOOK, handed to the agent.
    def tool_executor(call: ToolCall) -> ToolResult:
        nonlocal pending_transfer, policy_denied

        # STEP 4a — POLICY ON EVERY TOOL CALL (full only).
        if mode == Mode.full:
            # >>> PLUG-IN POINT: Muzammil's policy.authorize(user, call) <<<
            decision = policy.authorize(user, call)
            if not decision.allowed:
                policy_denied = True
                events.log_event(
                    user.id, mode_name, "policy_denied", "high",
                    "Denied: tool call rejected by policy", {"tool": call.name},
                )
                # The model sees only a short, data-free denial. The detailed
                # reason stays in the security event, never in the tool reply.
                return ToolResult(ok=False, data={}, error=chatbot.POLICY_DENIAL_ERROR)

            # STEP 4b — CONFIRMATION FOR TRANSFERS (full only; NOT executed).
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

        # STEP 5 — EXECUTE (bank_api and search_faq stamp their own audit rows).
        result = _dispatch(call)
        executed_tools.append(call)
        if result.ok:
            verified_facts.setdefault(call.name, []).append(result.data)
        return result

    # STEP 6 — AGENT / MOCK LLM (same call in all modes, same session history).
    output = chatbot.run_agent(user, req.message, history, tool_executor, docs)
    reply = output.reply
    if policy_denied and not reply.strip():
        reply = chatbot.DENIED_USER_MESSAGE

    # STEP 7 — RESPONSE GUARD (full only).
    if mode == Mode.full:
        # >>> PLUG-IN POINT: Muzammil's response_guard.check(...) <<<
        guard = response_guard.check(user, reply, verified_facts=verified_facts)
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

    if not blocked:
        _remember_turn(history_key, req.message, reply)

    return ChatResponse(
        reply=reply,
        blocked=blocked,
        pending_transfer=pending_transfer,
        executed_tools=executed_tools,
        detection=detection,
        latency_ms=(time.perf_counter() - started) * 1000,
    )
