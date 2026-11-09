"""One immutable search index: FAISS and BM25 built from the same chunks, ported from Team-D-II.

A snapshot is built whole and swapped in with one assignment, so a search never sees half of an
update. Filters pick the allowed chunks first, so filtered-out chunks never take a top-k slot.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from app.rag.chunking import Chunk


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    chunk: Chunk
    embedding: np.ndarray
    tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchFilters:
    category: str | None = None
    role_id: str | None = None

    def is_empty(self) -> bool:
        return self.category is None and self.role_id is None

    def accepts(self, chunk: Chunk) -> bool:
        return (self.category is None or chunk.category == self.category) and (
            self.role_id is None or chunk.role_id == self.role_id
        )


class Snapshot:
    def __init__(self, records: Sequence[IndexedChunk], *, dimension: int) -> None:
        self.records = tuple(records)
        # Inner product on normalised vectors = cosine similarity; ids = positions.
        self._faiss = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
        if self.records:
            vectors = np.vstack([r.embedding for r in self.records]).astype(np.float32)
            self._faiss.add_with_ids(vectors, np.arange(len(self.records), dtype=np.int64))
        corpus = [list(r.tokens) for r in self.records]
        self._bm25 = BM25Okapi(corpus) if any(corpus) else None

    def allowed(self, filters: SearchFilters) -> np.ndarray | None:
        """Positions that pass the filters; None means every chunk (no filter given)."""
        if filters.is_empty():
            return None
        positions = [i for i, r in enumerate(self.records) if filters.accepts(r.chunk)]
        return np.array(positions, dtype=np.int64)

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
        self, vector: np.ndarray, allowed: np.ndarray | None, k: int
    ) -> list[tuple[int, float]]:
        limit = len(self.records) if allowed is None else len(allowed)
        if limit == 0:
            return []
        # Keep the selector in a variable: FAISS does not hold a Python reference to it.
        selector = None if allowed is None else faiss.IDSelectorBatch(allowed)
        params = None if selector is None else faiss.SearchParameters(sel=selector)
        scores, ids = self._faiss.search(
            np.asarray([vector], dtype=np.float32), min(k, limit), params=params
        )
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0], strict=True) if i != -1]
