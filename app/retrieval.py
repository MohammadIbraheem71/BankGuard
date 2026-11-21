"""Document retrieval scaffolding. Owner: Ibraheem.

TODO(ibraheem): rank data/docs/*.md plus temp docs instead of returning [].
"""
from __future__ import annotations

from .models import Doc

_temp_docs: dict[str, Doc] = {}


def search(query: str, k: int = 3) -> list[Doc]:
    """Return up to k documents for `query`; empty until ranking is built."""
    # TODO(ibraheem): implement retrieval over data/docs/ and _temp_docs.
    return []


def add_temp_doc(doc: Doc) -> None:
    """Register an in-memory document (e.g. an eval cases' poisoned doc)."""
    _temp_docs[doc.id] = doc


def clear_temp_docs() -> None:
    """Remove all in-memory documents registered by add_temp_doc."""
    _temp_docs.clear()
