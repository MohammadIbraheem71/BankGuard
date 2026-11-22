"""Document retrieval over the synthetic FAQ corpus. Owner: Ibraheem.

A small dependency-free TF-IDF ranker is enough for the demo. Injected temp
documents (e.g. an eval case's poisoned doc) are always placed in the top-k so
the agent really sees them; that is what makes the baseline vulnerable.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .config import BASE_DIR
from .models import Doc

DOCS_DIR = BASE_DIR / "data" / "docs"

_temp_docs: dict[str, Doc] = {}


def _tokens(text: str) -> list[str]:
    """Lowercase words with a tiny plural normalization."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words]


def _file_docs() -> list[Doc]:
    """Load every synthetic markdown FAQ as a trusted Doc."""
    docs: list[Doc] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = next(
            (line[2:].strip() for line in text.splitlines() if line.startswith("# ")),
            path.stem,
        )
        docs.append(Doc(id=path.stem, title=title, text=text, trusted=True))
    return docs


def _rank(query: str, docs: list[Doc]) -> list[tuple[Doc, float]]:
    """Cosine-similarity TF-IDF ranking, stable for equal scores."""
    doc_tokens = [_tokens(f"{doc.title} {doc.text}") for doc in docs]
    n = len(docs)
    df: Counter[str] = Counter()
    for tokens in doc_tokens:
        df.update(set(tokens))
    idf = {term: math.log((1 + n) / (1 + count)) + 1 for term, count in df.items()}

    query_counts = Counter(_tokens(query))
    query_norm = math.sqrt(
        sum((1 + math.log(c)) ** 2 * idf.get(t, 0.0) ** 2 for t, c in query_counts.items())
    )
    scored: list[tuple[Doc, float]] = []
    for doc, tokens in zip(docs, doc_tokens):
        counts = Counter(tokens)
        dot = sum(
            (1 + math.log(counts[t])) * idf.get(t, 0.0) * (1 + math.log(c)) * idf.get(t, 0.0)
            for t, c in query_counts.items()
            if t in counts
        )
        doc_norm = math.sqrt(
            sum((1 + math.log(c)) ** 2 * idf.get(t, 0.0) ** 2 for t, c in counts.items())
        )
        score = dot / (query_norm * doc_norm) if query_norm and doc_norm else 0.0
        scored.append((doc, score))
    scored.sort(key=lambda item: -item[1])
    return scored


def search(query: str, k: int = 3) -> list[Doc]:
    """Return up to k docs, with injected temp docs guaranteed a slot."""
    all_docs = _file_docs() + list(_temp_docs.values())
    if not all_docs or k <= 0:
        return []
    ranked = _rank(query, all_docs)
    temp_ids = set(_temp_docs)
    temp_ranked = [(doc, score) for doc, score in ranked if doc.id in temp_ids]
    file_ranked = [(doc, score) for doc, score in ranked if doc.id not in temp_ids]
    selected = [doc for doc, _ in temp_ranked[:k]]
    chosen_ids = {doc.id for doc in selected}
    selected.extend(doc for doc, _ in file_ranked if doc.id not in chosen_ids)
    return selected[:k]


def add_temp_doc(doc: Doc) -> None:
    """Register an in-memory document (e.g. an eval case's poisoned doc)."""
    _temp_docs[doc.id] = doc


def clear_temp_docs() -> None:
    """Remove all in-memory documents registered by add_temp_doc."""
    _temp_docs.clear()
