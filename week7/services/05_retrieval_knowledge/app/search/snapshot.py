"""One immutable search index: FAISS and BM25 built from the same chunks.

A snapshot is built whole and swapped in with one assignment, so BM25 and FAISS always
describe the same chunk set (CONTRACT §6) and a search never sees half of an update.
Filters pick the allowed chunks first, so filtered-out chunks never take a top-k slot.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from app.kb.documents import Chunk, Document


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    chunk: Chunk
    document: Document
    embedding: np.ndarray
    tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchFilters:
    category: tuple[str, ...] | None = None
    season: str | None = None
    matchweek: int | None = None
    team_ids: tuple[int, ...] | None = None
    date_from: str | None = None
    date_to: str | None = None
    topic: tuple[str, ...] | None = None  # CONTRACT v1.15: the document's topic must be listed

    def is_empty(self) -> bool:
        return all(
            value is None
            for value in (
                self.category,
                self.season,
                self.matchweek,
                self.team_ids,
                self.date_from,
                self.date_to,
                self.topic,
            )
        )

    def accepts(self, document: Document) -> bool:
        if self.category is not None and document.category not in self.category:
            return False
        if self.season is not None and document.season != self.season:
            return False
        if self.matchweek is not None and document.matchweek != self.matchweek:
            return False
        if self.team_ids is not None and not set(self.team_ids) & set(document.team_ids):
            return False
        if self.topic is not None and document.topic not in self.topic:
            return False
        if self.date_from is not None or self.date_to is not None:
            # A date filter asks about a period; documents without a date are not in it.
            if document.date is None:
                return False
            if self.date_from is not None and document.date < self.date_from:
                return False
            if self.date_to is not None and document.date > self.date_to:
                return False
        return True


class Snapshot:
    def __init__(
        self, records: Sequence[IndexedChunk], *, dimension: int, index_version: str | None
    ) -> None:
        self.records = tuple(records)
        self.dimension = dimension
        self.index_version = index_version
        # Inner product on normalised vectors = cosine similarity; ids = positions.
        self._faiss = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
        if self.records:
            vectors = np.vstack([r.embedding for r in self.records]).astype(np.float32)
            self._faiss.add_with_ids(vectors, np.arange(len(self.records), dtype=np.int64))
        corpus = [list(r.tokens) for r in self.records]
        self._bm25 = BM25Okapi(corpus) if any(corpus) else None

    @property
    def size(self) -> int:
        return len(self.records)

    @property
    def faiss_count(self) -> int:
        return int(self._faiss.ntotal)

    @property
    def bm25_count(self) -> int:
        return int(self._bm25.corpus_size) if self._bm25 else 0

    def allowed(self, filters: SearchFilters) -> np.ndarray | None:
        """Positions that pass the filters; None means every chunk (no filter given)."""
        if filters.is_empty():
            return None
        return np.array(
            [i for i, r in enumerate(self.records) if filters.accepts(r.document)], dtype=np.int64
        )

    def bm25_top(
        self, tokens: Sequence[str], allowed: np.ndarray | None, k: int
    ) -> list[tuple[int, float]]:
        if self._bm25 is None or not tokens:
            return []
        scores = np.asarray(self._bm25.get_scores(list(tokens)), dtype=np.float64)
        if allowed is not None:
            mask = np.full(scores.shape, -np.inf)
            mask[allowed] = 0.0
            scores = scores + mask
        order = np.argsort(-scores, kind="stable")[:k]
        # Zero means no query word matched: not a hit.
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0]

    def vector_top(
        self, vector: np.ndarray, allowed: np.ndarray | None, k: int, min_score: float
    ) -> list[tuple[int, float]]:
        limit = self.size if allowed is None else len(allowed)
        if limit == 0:
            return []
        # Keep the selector in a variable: FAISS does not hold a Python reference to it.
        selector = None if allowed is None else faiss.IDSelectorBatch(allowed)
        params = None if selector is None else faiss.SearchParameters(sel=selector)
        scores, ids = self._faiss.search(
            np.asarray([vector], dtype=np.float32), min(k, limit), params=params
        )
        return [
            (int(i), float(s))
            for i, s in zip(ids[0], scores[0], strict=True)
            if i != -1 and (min_score <= 0 or s >= min_score)
        ]
