"""Prevent disclosure and compare outbound monetary claims to verified tool data."""
from __future__ import annotations

import re
from contextlib import closing
from decimal import Decimal, InvalidOperation

from app import db
from app.models import GuardResult, User

_CANARY = re.compile(r"\bCANARY(?:-[A-Z0-9]+)+\b", re.IGNORECASE)
_SYSTEM_DISCLOSURE = re.compile(
    r"\b(?:you are bankguard, a synthetic banking assistant|"
    r"the signed-in customer is .{0,80}your account_ids are|"
    r"you have four tools\. tool arguments)\b"
    r"|<\/?(?:system(?:_prompt)?|retrieved_documents)>"
    r"|(?:^|[.!?\n])\s*(?:[#>*-]+\s*)?(?:here (?:is|are) (?:my|the)\s+|begin\s+)?"
    r"(?:system prompt|system instructions|developer message|developer instructions)\s*(?::|$)",
    re.IGNORECASE,
)
_CURRENCY = r"(?:PKR|Rs\.?|₨)"
_NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_MONEY = rf"(?:{_CURRENCY}\s*)?(?P<amount>{_NUMBER})(?![\d,]|\.\d)(?:\s*{_CURRENCY}\b)?(?![\w])"
_ACCOUNT_LABEL = r"account\s*(?:id|number|no\.)?\s*[:#]?\s*"
_BALANCE_CLAIM = re.compile(
    rf"(?:\b{_ACCOUNT_LABEL}(?P<subject>\d+)(?:\s+has\s+(?:an?\s+)?|\s*:\s*)"
    rf"(?:current\s+|available\s+)?)?"
    rf"\bbalance"
    rf"(?:\s+(?:for|of|on)\s+(?:your\s+)?{_ACCOUNT_LABEL}(?P<account>\d+)\b)?"
    rf"(?:\s+(?:is|was|of|stands\s+at)\s+|\s*[:=]\s*|\s+){_MONEY}",
    re.IGNORECASE,
)
_TRANSFER_CLAIM = re.compile(
    rf"\b(?:transfer(?:\s+amount)?(?:\s+(?:of|is|was)|\s*[:=])|transferred|sent|debited)"
    rf"\s*{_MONEY}",
    re.IGNORECASE,
)

FINDINGS = frozenset({
    "canary", "other_customer_identifier", "masked_customer_identifier",
    "system_prompt", "unverified_amount",
})


def _identifier_pattern(value: str) -> re.Pattern[str]:
    if re.fullmatch(r"[+\d\s-]+", value) and any(char.isdecimal() for char in value):
        digits = re.sub(r"\D", "", value)
        separator = r"[\s-]*"
        formatted = separator.join(digits)
        if value.startswith("+92") and digits.startswith("92"):
            local = separator.join("0" + digits[2:])
            formatted = rf"(?:\+?{formatted}|{local})"
        return re.compile(rf"(?<![\w+]){formatted}(?!\w)")
    return re.compile(rf"(?<![\w@]){re.escape(value)}(?![\w@])", re.IGNORECASE)


def _masked(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    suffix = digits[-4:] if len(digits) >= 4 else value[-4:]
    return f"****{suffix}"


def _protected_identifiers(user_id: int) -> tuple[list[str], list[str]]:
    with closing(db.get_conn()) as conn:
        users = conn.execute("SELECT id, cnic, phone, email FROM users").fetchall()
        accounts = conn.execute("SELECT user_id, account_number FROM accounts").fetchall()

    others: list[str] = []
    own: list[str] = []
    for row in users:
        if row["id"] == user_id:
            own.append(row["cnic"])
        else:
            others.extend((row["cnic"], row["phone"], row["email"]))
    for row in accounts:
        values = own if row["user_id"] == user_id else others
        values.append(row["account_number"])
    return (
        sorted(set(others) - {""}, key=len, reverse=True),
        sorted(set(own) - {""}, key=len, reverse=True),
    )


def _decimal(value) -> Decimal | None:
    try:
        number = Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _contradicts_verified_amount(text: str, facts: dict) -> bool:
    text = text.replace("**", "").replace("__", "").replace("`", "")
    balances: dict[str | None, set[Decimal]] = {}
    transfers: set[Decimal] = set()

    def add_balance(account, amount) -> None:
        number = _decimal(amount)
        if number is not None:
            key = str(account) if account is not None else None
            balances.setdefault(key, set()).add(number)

    add_balance(None, facts.get("balance"))
    for result in facts.get("get_balance", ()):
        add_balance(result.get("account_id"), result.get("balance"))
    transfer_amounts = [facts.get("transfer_amount")]
    for result in facts.get("create_transfer", ()):
        add_balance(result.get("from_account_id"), result.get("new_balance"))
        transfer_amounts.append(result.get("amount"))
    transfers.update(number for amount in transfer_amounts if (number := _decimal(amount)) is not None)

    all_balances = set().union(*balances.values())
    for claim in _BALANCE_CLAIM.finditer(text):
        account = claim.group("account") or claim.group("subject")
        verified = balances.get(account, balances.get(None, set())) if account else all_balances
        if verified and _decimal(claim.group("amount")) not in verified:
            return True
    return bool(transfers) and any(
        _decimal(claim.group("amount")) not in transfers for claim in _TRANSFER_CLAIM.finditer(text)
    )


def _verified_transaction_canaries(user: User, facts: dict) -> set[str]:
    return {
        match.group().casefold()
        for result in facts.get("get_transactions", ())
        if result.get("account_id") in user.account_ids
        for transaction in result.get("transactions", ())
        for match in _CANARY.finditer(transaction.get("description", ""))
    }


def check(user: User, text: str, verified_facts: dict | None = None) -> GuardResult:
    if _SYSTEM_DISCLOSURE.search(text):
        return GuardResult(
            safe=False, text="BankGuard cannot show internal instructions.", findings=["system_prompt"]
        )

    findings: list[str] = []
    if verified_facts and _contradicts_verified_amount(text, verified_facts):
        return GuardResult(
            safe=False, text="BankGuard could not verify the amount in this reply.", findings=["unverified_amount"]
        )

    canaries = {match.group().casefold() for match in _CANARY.finditer(text)}
    unsafe = False
    if canaries:
        unsafe = bool(canaries - _verified_transaction_canaries(user, verified_facts or {}))
        text = _CANARY.sub("[redacted]", text)
        findings.append("canary")

    others, own = _protected_identifiers(user.id)
    for values, finding, mask in (
        (others, "other_customer_identifier", False),
        (own, "masked_customer_identifier", True),
    ):
        for value in values:
            replacement = _masked(value) if mask else "[redacted]"
            text, count = _identifier_pattern(value).subn(lambda _: replacement, text)
            if count:
                unsafe = True
                if finding not in findings:
                    findings.append(finding)

    return GuardResult(safe=not unsafe, text=text, findings=findings)
