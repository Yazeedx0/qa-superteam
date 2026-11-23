"""BM25 retriever over the Northwind Goods policy corpus.

The corpus is a handful of Markdown files, so the whole index is built in
memory at import time. Document ids are the corpus file names
(for example ``"refunds.md"``).
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "corpus"

# Standard BM25 parameters.
K1 = 1.5
B = 0.75

STOPWORDS = frozenset(
    """
    a about after an and any are as at be been by can could do does for from
    get got had has have how i if in into is it its me my of on or our please
    should so than that the their them then there these they this to too us
    was we were what when where which who why will with would you your
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase ``text`` and split it into terms, dropping stopwords."""
    return [tok for tok in text.lower().split() if tok not in STOPWORDS]


def _load_corpus() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(CORPUS_DIR.glob("*.md"))}


DOCS: dict[str, str] = _load_corpus()


class _BM25Index:
    def __init__(self, docs: dict[str, str]) -> None:
        self.term_counts = {doc_id: Counter(tokenize(text)) for doc_id, text in docs.items()}
        self.lengths = {doc_id: sum(counts.values()) for doc_id, counts in self.term_counts.items()}
        self.avg_length = sum(self.lengths.values()) / max(len(self.lengths), 1)

        doc_freq: Counter[str] = Counter()
        for counts in self.term_counts.values():
            doc_freq.update(counts.keys())
        n_docs = len(docs)
        self.idf = {
            term: math.log((n_docs - freq + 0.5) / (freq + 0.5) + 1.0) for term, freq in doc_freq.items()
        }

    def score(self, query_terms: list[str], doc_id: str) -> float:
        counts = self.term_counts[doc_id]
        length_norm = K1 * (1.0 - B + B * self.lengths[doc_id] / self.avg_length)
        total = 0.0
        for term in query_terms:
            freq = counts.get(term, 0)
            if freq:
                total += self.idf[term] * freq * (K1 + 1.0) / (freq + length_norm)
        return total


_INDEX = _BM25Index(DOCS)


def get_document(doc_id: str) -> str:
    """Return the raw Markdown text of a corpus document."""
    return DOCS[doc_id]


def retrieve(query: str, k: int = 3) -> list[tuple[str, float, str]]:
    """Return up to ``k`` ``(doc_id, score, text)`` tuples, best match first.

    Documents that share no terms with the query are not returned.
    Ties are broken by document id so results are deterministic.
    """
    terms = tokenize(query)
    scored = [(doc_id, _INDEX.score(terms, doc_id)) for doc_id in DOCS]
    scored = [(doc_id, score) for doc_id, score in scored if score > 0.0]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [(doc_id, round(score, 4), DOCS[doc_id]) for doc_id, score in scored[:k]]
