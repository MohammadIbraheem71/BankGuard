from contextlib import closing

import pytest

from app import db
from app.security.events import list_events, log_event

pytestmark = pytest.mark.usefixtures("seeded_bank")


def test_sanitizes_summary_and_metadata_before_insert():
    protected_text = "CANARY-BOB-4482 bob@example.test"
    log_event(1, "full", "blocked_user_message", "high", protected_text, {
        "categories": ["role_impersonation", protected_text, {"nested": protected_text}],
        "message": protected_text,
    })
    with closing(db.get_conn()) as conn:
        row = conn.execute("SELECT summary, details_json FROM security_events").fetchone()
    assert row["summary"] == "Blocked: user message flagged"
    assert row["details_json"] == '{"categories": ["role_impersonation"]}'


def test_lists_newest_first_with_filters():
    log_event(1, "full", "policy_denied", "high", "", {"tool": "get_balance"})
    log_event(1, "baseline", "chat_completed", "low", "", {"blocked": False})
    log_event(1, "full", "response_guard_blocked", "high", "", {"findings": ["canary"]})
    assert [event.event_type for event in list_events()] == [
        "response_guard_blocked", "chat_completed", "policy_denied",
    ]
    assert list_events(mode="full", limit=1)[0].details == {"findings": ["canary"]}
    assert list_events(mode="detector_only") == []
    assert list_events(limit=0) == []
    assert list_events(limit=-1) == []


def test_legacy_event_is_redacted_when_listed():
    with closing(db.get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO security_events (ts, user_id, mode, event_type, severity, summary, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-01-01T00:00:00Z", 1, "full", "transfer_pending", "medium",
             "CANARY-ALICE-7731", '{"id": "private-transfer-id"}'),
        )
    event = list_events()[0]
    assert event.summary == "Pending transfer awaits user confirmation"
    assert event.details == {}


def test_unknown_event_text_is_replaced_by_generic_type():
    log_event(1, "full", "untrusted message", "low", "raw summary", [])
    event = list_events()[0]
    assert event.event_type == "security_event"
    assert event.summary == "Security event recorded"
    assert event.details == {}


@pytest.mark.parametrize(("mode", "severity"), [("unknown", "high"), ("full", "unexpected")])
def test_rejects_invalid_mode_or_severity(mode, severity):
    with pytest.raises(ValueError, match="Invalid security event"):
        log_event(1, mode, "policy_denied", severity, "", {})
    assert list_events() == []
