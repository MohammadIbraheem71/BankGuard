"""Validate and authorize tool calls independently of the language model."""
from __future__ import annotations

import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app import db
from app.models import PolicyDecision, ToolCall, User

MAX_TRANSFER_PKR = 100_000
_RECIPIENT_REF = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")


class _ToolArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class _BalanceArgs(_ToolArgs):
    account_id: int = Field(gt=0)


class _TransactionsArgs(_BalanceArgs):
    limit: int = Field(default=10, gt=0, le=2**63 - 1)


class _TransferArgs(_ToolArgs):
    from_account_id: int = Field(gt=0)
    to_account_ref: str = Field(max_length=64)
    amount: float = Field(gt=0, le=MAX_TRANSFER_PKR, allow_inf_nan=False)

    @field_validator("to_account_ref")
    @classmethod
    def validate_recipient(cls, value: str) -> str:
        if not _RECIPIENT_REF.fullmatch(value):
            raise ValueError("Invalid recipient reference")
        return value

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float) -> float:
        cents = Decimal(str(value)) * 100
        if cents != cents.to_integral_value():
            raise ValueError("Amount must have at most two decimal places")
        return value


class _SearchArgs(_ToolArgs):
    query: str


_SCHEMAS = {
    "get_balance": _BalanceArgs,
    "get_transactions": _TransactionsArgs,
    "create_transfer": _TransferArgs,
    "search_faq": _SearchArgs,
}

_VALIDATION_REASONS = {
    "account_id": "Account ID must be a positive integer.",
    "limit": "Transaction limit must be a positive integer in the supported range.",
    "from_account_id": "Source account ID must be a positive integer.",
    "to_account_ref": "Invalid recipient reference.",
    "amount": f"Amount must be positive, at most PKR {MAX_TRANSFER_PKR:,}, and have at most two decimal places.",
    "query": "FAQ query must be a string.",
}


def _is_source_reference(account_id: int, recipient: str) -> bool:
    if recipient.isdecimal() and int(recipient) == account_id:
        return True
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT account_number FROM accounts WHERE id = ?", (account_id,)).fetchone()
    finally:
        conn.close()
    return row is not None and row["account_number"].casefold() == recipient.casefold()


def authorize(user: User, call: ToolCall) -> PolicyDecision:
    if user.role != "customer":
        return PolicyDecision(allowed=False, reason="This role cannot use banking tools.")

    schema = _SCHEMAS.get(call.name) if isinstance(call.name, str) else None
    if schema is None:
        return PolicyDecision(allowed=False, reason="Tool is not on the allowlist.")
    try:
        args = schema.model_validate(call.args)
    except ValidationError as exc:
        error = exc.errors(include_input=False)[0]
        reason = "Unexpected tool arguments."
        if error["type"] != "extra_forbidden" and error["loc"]:
            reason = _VALIDATION_REASONS.get(error["loc"][0], "Invalid tool arguments.")
        return PolicyDecision(allowed=False, reason=reason)

    if isinstance(args, _BalanceArgs) and args.account_id not in user.account_ids:
        return PolicyDecision(allowed=False, reason="The account is not owned by the signed-in customer.")
    if isinstance(args, _TransferArgs):
        if args.from_account_id not in user.account_ids:
            return PolicyDecision(allowed=False, reason="The source account is not owned by the signed-in customer.")
        if _is_source_reference(args.from_account_id, args.to_account_ref):
            return PolicyDecision(allowed=False, reason="The recipient must differ from the source account.")
        return PolicyDecision(allowed=True, reason="Transfer requires confirmation.", requires_confirmation=True)

    return PolicyDecision(allowed=True, reason="Allowed by tool policy.")
