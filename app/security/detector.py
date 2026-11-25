"""Explainable prompt-injection detection for user text and retrieved documents."""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from app.models import DetectionResult

THRESHOLD = 0.65

_INVISIBLE = str.maketrans(
    "", "",
    "\u00ad\u061c\u180e\u200b\u200c\u200d\u200e\u200f"
    "\u202a\u202b\u202c\u202d\u202e\u2060\u2066\u2067\u2068\u2069\ufeff",
)
_LEET = str.maketrans("013457@$", "oieastas")
_LEET_WORD = re.compile(r"(?<!\w)[a-z0-9@$]+(?!\w)")
_ENCODED_SPAN = re.compile(r"(?<![\w+/=-])[A-Za-z0-9+/_-]{48,}={0,2}(?![\w+/=-])")
_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)

_RULES = (
    (
        "instruction_override",
        0.80,
        "Text attempts to override the assistant's instructions.",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+)?(?:the\s+|your\s+)?"
            r"(?:(?:previous|prior|earlier|original|system|developer|security)\s+"
            r"(?:instructions?|rules?|prompts?|polic(?:y|ies))|system\s+prompt)\b"
            r"|\b(?:follow|use|obey)\s+(?:these\s+|my\s+|the\s+)?new\s+rules\b"
            r"|^(?:new\s+rules|developer\s+mode)[.!:]?$"
            r"|\b(?:enable|activate|enter|switch\s+to)\s+developer\s+mode\b"
            r"|\b(?:pichl[iey]+|purani|pehli)\s+(?:hidayaat?|hidayat(?:ain|en)?|instructions?|rules?)\s+"
            r"(?:ko\s+)?(?:bhool(?:\s+(?:jao|jaen))?|(?:nazar\s*andaz|ignore)\s+karo)\b"
            r"|(?:پچھلی|پہلی|پرانی|سابقہ)\s+ہدایات\s+(?:کو\s+)?(?:نظر\s*انداز\s+کر[ویں]+|بھول\s+جا[ؤو])"
        ),
    ),
    (
        "role_impersonation",
        0.70,
        "Text claims a privileged system, developer, or bank role.",
        re.compile(
            r"\b(?:i\s+am|i['’]m)\s+(?:(?:the|an?|your)\s+)?"
            r"(?:admin(?:istrator)?|(?:bank\s+)?manager|bank\s+staff|developer)\b"
            r"|\bas\s+your\s+(?:developer|administrator)\b"
            r"|(?:^|[.!?]\s+|^#{1,6}\s+|\[|<)system\s*(?::|\]|>)"
            r"|\b(?:main|mein|mai)\s+(?:bank\s+(?:ka\s+)?)?(?:admin|manager)\s+(?:hoon|hun)\b"
            r"|میں\s+(?:بینک\s+(?:کا\s+)?)?(?:منیجر|ایڈمن)\s+ہوں"
        ),
    ),
    (
        "data_extraction",
        0.75,
        "Text requests protected customer data or internal instructions.",
        re.compile(
            r"\b(?:show|list|reveal|print|dump|export|disclose|give\s+me)\s+"
            r"(?:me\s+)?(?:(?:all|every)\s+(?:(?:bank|customer)\s+)?accounts?\b"
            r"(?!\s+(?:(?:that\s+)?i\s+own|(?:in|under)\s+my\s+name|"
            r"(?:linked|registered|belonging)\s+to\s+(?:my\s+profile|me))\s*[.?!]?$)"
            r"|(?:other|all)\s+customers?(?:['’]s?)?\b"
            r"|(?:another|other)\s+(?:user|customer)s?['’]?s?\s+(?:account|transactions?|balance|data)\b"
            r"|(?:your|the|hidden|internal)\s+(?:(?:hidden|internal)\s+)?"
            r"(?:system\s+prompt|developer\s+(?:prompt|instructions?)|system\s+instructions?)\b)"
            r"|\b(?:sab|tamam)\s+(?:ke\s+)?(?:accounts?|khaat[ey])\s+(?:dikhao|batao)\b"
            r"|(?:تمام|سب)\s+(?:بینک\s+)?(?:اکاؤنٹس|کھاتے)\s+(?:دکھا[ؤو]|بتا[ؤو])"
        ),
    ),
)
_DOCUMENT_DIRECTIONS = re.compile(
    r"\b(?:assistant|chatbot|language model|ai agent)\s*[,;:]\s*"
    r"(?:you\s+must|please\s+|(?:always|never)\s+|(?:call|invoke|send|reveal)\b)"
    r"|\b(?:the\s+)?(?:assistant|chatbot|language model|ai agent)\s+"
    r"(?:must|should|is\s+required\s+to)\b"
    r"|\b(?:call|invoke|execute|use|run)\s+(?:the\s+)?"
    r"(?:get_balance|get_transactions|create_transfer|search_faq|(?:banking\s+)?tool\b)"
    r"|\b(?:send|export|forward|disclose)\s+(?:the\s+)?"
    r"(?:customer data|customer records|account credentials|tool (?:output|results?))\b"
)


def _leet_word(match: re.Match[str]) -> str:
    word = match.group()
    return word.translate(_LEET) if re.search(r"[a-z]", word) else word


def _looks_encoded(text: str) -> bool:
    for match in _ENCODED_SPAN.finditer(text):
        span = match.group()
        if re.search(r"[A-Z]", span) and re.search(r"[a-z]", span) and re.search(r"[0-9+/_=-]", span):
            return True
    return False


def _has_document_directions(text: str) -> bool:
    return bool(_DOCUMENT_DIRECTIONS.search(text)) or any(
        pattern.search(comment.group()[4:])
        for comment in _HTML_COMMENT.finditer(text)
        for _, _, _, pattern in _RULES
    )


def inspect(text: str, source: Literal["user", "document"] = "user") -> DetectionResult:
    clean = unicodedata.normalize("NFKC", text).translate(_INVISIBLE)
    normalized = " ".join(clean.lower().split())
    variants = (normalized, _LEET_WORD.sub(_leet_word, normalized))
    categories: list[str] = []
    reasons: list[str] = []
    score = 0.0

    for category, weight, reason, pattern in _RULES:
        if any(pattern.search(variant) for variant in variants):
            categories.append(category)
            reasons.append(reason)
            score += weight

    if source == "document" and any(_has_document_directions(variant) for variant in variants):
        categories.append("embedded_document_instruction")
        reasons.append("Retrieved document contains instructions directed at the assistant.")
        score += 0.85

    if _looks_encoded(clean):
        categories.append("obfuscation")
        reasons.append("Text contains a long encoded-looking span.")
        score += 0.65

    score = round(min(score, 1.0), 2)
    return DetectionResult(flagged=score >= THRESHOLD, score=score, categories=categories, reasons=reasons)
