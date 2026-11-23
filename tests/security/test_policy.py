import pytest

from app.models import ToolCall
from app.security.policy import MAX_TRANSFER_PKR, authorize


@pytest.mark.parametrize(("tool", "args"), [
    ("get_balance", {"account_id": 1001}),
    ("get_transactions", {"account_id": 1002}),
    ("get_transactions", {"account_id": 1002, "limit": 3}),
    ("search_faq", {"query": "What are the fees?"}),
])
def test_allowed_calls_do_not_require_confirmation(alice, tool, args):
    decision = authorize(alice, ToolCall(name=tool, args=args))
    assert decision.allowed
    assert not decision.requires_confirmation


@pytest.mark.parametrize(("tool", "args"), [
    ("get_balance", {"account_id": 2001}),
    ("get_transactions", {"account_id": 2001}),
    ("get_balance", {"account_id": "1001"}),
    ("get_balance", {"account_id": True}),
    ("get_balance", {"account_id": 1001.0}),
    ("get_balance", {}),
    ("get_balance", {"account_id": 1001, "role": "admin"}),
    ("get_transactions", {"account_id": 1001, "limit": -1}),
    ("get_transactions", {"account_id": 1001, "limit": 2**63}),
    ("search_faq", {"query": 42}),
    ("search_faq", {"query": "fees", "user": "someone"}),
])
def test_denied_calls(alice, tool, args):
    decision = authorize(alice, ToolCall(name=tool, args=args))
    assert not decision.allowed
    assert not decision.requires_confirmation
    assert decision.reason


@pytest.mark.parametrize("tool", ["unknown", []])
def test_rejects_tool_outside_allowlist(alice, tool):
    call = ToolCall.model_construct(name=tool, args={})
    assert not authorize(alice, call).allowed


def test_rejects_role_outside_contract(alice):
    user = alice.model_copy(update={"role": "administrator"})
    assert not authorize(user, ToolCall(name="get_balance", args={"account_id": 1001})).allowed


@pytest.mark.parametrize(("field", "value"), [
    ("from_account_id", 2001),
    ("amount", 0),
    ("amount", -1),
    ("amount", 1.001),
    ("amount", MAX_TRANSFER_PKR + 0.01),
    ("amount", "1.20"),
    ("amount", True),
    ("amount", float("nan")),
    ("amount", float("inf")),
    ("to_account_ref", "1001"),
    ("to_account_ref", "0001001"),
    ("to_account_ref", "pkr-1001-chk"),
    ("to_account_ref", "reference with spaces"),
    ("to_account_ref", "REFERENCE--01"),
    ("to_account_ref", "a" * 65),
])
def test_rejects_invalid_transfers(seeded_bank, alice, field, value):
    args = {"from_account_id": 1001, "to_account_ref": "EXT-001", "amount": 1}
    args[field] = value
    decision = authorize(alice, ToolCall(name="create_transfer", args=args))
    assert not decision.allowed
    assert not decision.requires_confirmation


@pytest.mark.parametrize(("recipient", "amount"), [
    ("2001", 10),
    ("2001", 0.01),
    ("EXT-001", 200.25),
    ("PKR-2001-CHK", MAX_TRANSFER_PKR),
])
def test_approved_transfer_always_requires_confirmation(seeded_bank, alice, recipient, amount):
    call = ToolCall(
        name="create_transfer",
        args={"from_account_id": 1001, "to_account_ref": recipient, "amount": amount},
    )
    decision = authorize(alice, call)
    assert decision.allowed
    assert decision.requires_confirmation
