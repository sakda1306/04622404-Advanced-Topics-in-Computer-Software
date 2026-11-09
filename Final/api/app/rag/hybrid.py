"""Hybrid search: BM25 + vector, fused with Reciprocal Rank Fusion (Design.md §6)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.rag.chunking import Chunk
from app.rag.embedder import Embedder
from app.rag.snapshot import SearchFilters, Snapshot
from app.rag.tokenize import tokenize

Mode = Literal["hybrid", "bm25", "vector"]

RRF_K = 60
_CANDIDATES = 20


@dataclass(frozen=True, slots=True)
class Hit:
    chunk: Chunk
    score: float  # RRF in hybrid mode; a single mode returns that method's own score
    bm25_score: float | None = None
    vector_score: float | None = None


def rrf(ranked_lists: Sequence[Sequence[int]], k: int) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, position in enumerate(ranked, start=1):
            scores[position] = scores.get(position, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def search(
    snapshot: Snapshot,
    embedder: Embedder,
    *,
    query: str,
    top_k: int,
    filters: SearchFilters,
    mode: Mode,
) -> list[Hit]:
    if not query.strip():
        return []
    allowed = snapshot.allowed(filters)
    if allowed is not None and len(allowed) == 0:
        return []

    bm25_hits: list[tuple[int, float]] = []
    vector_hits: list[tuple[int, float]] = []
    if mode in ("hybrid", "bm25"):
        bm25_hits = snapshot.bm25_top(tokenize(query), allowed, _CANDIDATES)
    if mode in ("hybrid", "vector"):
        vector_hits = snapshot.vector_top(embedder.encode_query(query), allowed, _CANDIDATES)

    if mode == "hybrid":
        fused = rrf([[p for p, _ in bm25_hits], [p for p, _ in vector_hits]], RRF_K)
    else:
        fused = bm25_hits if mode == "bm25" else vector_hits
    bm25_scores, vector_scores = dict(bm25_hits), dict(vector_hits)
    return [
        Hit(snapshot.records[p].chunk, s, bm25_scores.get(p), vector_scores.get(p))
        for p, s in fused[:top_k]
    ]
