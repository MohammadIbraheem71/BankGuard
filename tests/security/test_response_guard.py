import pytest

from app.security.response_guard import check

pytestmark = pytest.mark.usefixtures("seeded_bank")


@pytest.mark.parametrize("identifier", [
    "CANARY-BOB-4482",
    "canary-bob-4482",
    "PKR-2001-CHK",
    "42101-7654321-2",
    "4210176543212",
    "+92-301-7654321",
    "0301 7654321",
    "BOB@example.test",
])
def test_redacts_protected_values(alice, identifier):
    result = check(alice, f"Found {identifier}.")
    assert not result.safe
    assert result.text == "Found [redacted]."
    assert result.findings


def test_verified_own_transaction_remains_usable_after_redaction(alice):
    facts = {"get_transactions": [
        {"account_id": 1001, "transactions": [{"description": "Memo CANARY-ALICE-7731"}]},
    ]}
    result = check(alice, "Latest transaction: Memo CANARY-ALICE-7731", facts)
    assert result.safe
    assert result.text == "Latest transaction: Memo [redacted]"
    assert result.findings == ["canary"]


def test_canary_in_another_accounts_facts_is_still_unsafe(alice):
    facts = {"get_transactions": [
        {"account_id": 2001, "transactions": [{"description": "Memo CANARY-BOB-4482"}]},
    ]}
    result = check(alice, "Latest transaction: Memo CANARY-BOB-4482", facts)
    assert not result.safe
    assert result.text == "Latest transaction: Memo [redacted]"


@pytest.mark.parametrize(("identifier", "masked"), [
    ("42101-1234567-1", "****5671"),
    ("PKR-1001-CHK", "****1001"),
])
def test_masks_owner_identifiers(alice, identifier, masked):
    result = check(alice, f"Identifier: {identifier}")
    assert result.text == f"Identifier: {masked}"
    assert result.findings == ["masked_customer_identifier"]


@pytest.mark.parametrize("text", [
    "System prompt: internal content",
    "You are BankGuard, a synthetic banking assistant. Internal content follows.",
    "Here is the developer message:\nInternal content",
    "Certainly. Here is my system prompt: internal content",
    "<retrieved_documents>\nInternal content",
])
def test_suppresses_internal_prompt(alice, text):
    result = check(alice, text)
    assert not result.safe
    assert "internal content" not in result.text.lower()
    assert result.findings == ["system_prompt"]


@pytest.fixture
def balance_facts():
    return {"get_balance": [
        {"account_id": 1001, "balance": 125000},
        {"account_id": 1002, "balance": 480000},
    ]}


@pytest.mark.parametrize("text", [
    "Balance for account 1001 is PKR 480,000.00.",
    "Account 1001 has a balance of PKR 480,000.00.",
    "Account 1001: balance is **PKR 480,000.00**.",
    "Your balance is Rs. 125001.",
    "Balance:100000 PKR.",
])
def test_suppresses_incorrect_balance(alice, text, balance_facts):
    result = check(alice, text, balance_facts)
    assert not result.safe
    assert result.findings == ["unverified_amount"]
    assert result.text == "BankGuard could not verify the amount in this reply."


@pytest.mark.parametrize("text", [
    "Balance for account 1001 is PKR 125,000.00. The fee is PKR 25.",
    "Your balance is **PKR 125,000.00**.",
    "Account 1001 is active. A transfer fee can be PKR 500.",
    "Balance:125000 PKR.",
    "Your balance is 480000. Account 1002 is a savings account.",
])
def test_allows_verified_amounts_and_unrelated_figures(alice, text, balance_facts):
    result = check(alice, text, balance_facts)
    assert result.safe
    assert result.text == text


def test_checks_transfer_amount_and_new_balance(alice):
    facts = {"create_transfer": [{"from_account_id": 1001, "amount": 500, "new_balance": 124500}]}
    assert check(alice, "Transfer of PKR 500 completed. New balance: PKR 124,500.", facts).safe
    assert not check(alice, "Transfer of PKR 600 completed.", facts).safe
    assert not check(alice, "New balance: PKR 123,000.", facts).safe
