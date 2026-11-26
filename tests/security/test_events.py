import json
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
             "CANARY-ALICE-7731", '{"id": "CANARY-ALICE-7731"}'),
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


def test_identifiers_round_trip_through_storage_and_http(alice):
    from fastapi.testclient import TestClient
    from app.auth import create_token
    from app.main import app

    expected = [
        {"id": "_TGmQ2bJATlBMkw8eq-pGs3w2LwdR3sh"},
        {"doc_id": "poison-e2e"},
        {"pending_id": "A" * 64, "account_id": 1001, "tool_name": "get_balance",
         "category": "data_extraction"},
    ]
    for event_type, details in zip(("transfer_pending", "blocked_document", "policy_denied"), expected):
        log_event(1, "full", event_type, "medium", "", details)
    with closing(db.get_conn()) as conn:
        rows = conn.execute("SELECT details_json FROM security_events ORDER BY id")
        assert [json.loads(row[0]) for row in rows] == expected
    with TestClient(app) as client:
        response = client.get("/events", headers={"Authorization": f"Bearer {create_token(alice)}"})
        assert response.status_code == 200
        assert [row["details"] for row in response.json()] == expected[::-1]


@pytest.mark.parametrize("value", [
    "", "x" * 65, "raw user text", "canary-bob-4482", "42101-7654321-2", 4210176543212,
    "bob@example.test", "0301-7654321", 923017654321, "ref.42101.7654321.2",
    True, None, {"id": "nested"}, ["array"], float("inf"), float("nan"),
])
def test_private_or_invalid_identifiers_are_dropped(value):
    log_event(1, "full", "blocked_document", "high", "", {"doc_id": value})
    with closing(db.get_conn()) as conn:
        assert conn.execute("SELECT details_json FROM security_events").fetchone()[0] == "{}"
    assert list_events()[0].details == {}


def test_numeric_identifier_and_unrecognized_names():
    log_event(1, "full", "policy_denied", "high", "", {
        "id": 31.5, "tool_name": "unknown", "category": "typo",
    })
    assert list_events()[0].details == {"id": 31.5}
