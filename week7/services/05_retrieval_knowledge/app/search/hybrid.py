"""Hybrid search (CONTRACT §4): BM25 + vector, fused with Reciprocal Rank Fusion.

- BM25 reads `query` (the router's English rewrite) plus official names of nicknamed teams
- the vector side reads `query` too: the Thai original matched English documents worse
  (eval, match set: hybrid hit@1 0.70 with it, 0.90 without); `query_original` is only
  searched for team nicknames
- hybrid `score` = RRF (k = 60); single modes return that method's raw score
- with a reranker, the fused candidates are re-ordered by `rerank_score`
05 never relaxes filters: the fallback order belongs to the router (CONTRACT §3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from app.core.logging import get_logger
from app.search.aliases import AliasIndex, AliasProvider
from app.search.embedder import Embedder
from app.search.reranker import Reranker
from app.search.snapshot import SearchFilters, Snapshot
from app.search.tokenize import tokenize

log = get_logger(__name__)

Mode = Literal["hybrid", "bm25", "vector"]


@dataclass(frozen=True, slots=True)
class Hit:
    position: int
    score: float
    bm25_score: float | None = None
    vector_score: float | None = None
    rerank_score: float | None = None


def rrf(ranked_lists: Sequence[Sequence[int]], k: int) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, position in enumerate(ranked, start=1):
            scores[position] = scores.get(position, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class Searcher:
    def __init__(
        self,
        embedder: Embedder,
        aliases: AliasIndex | AliasProvider,
        *,
        reranker: Reranker | None,
        candidate_k: int,
        rrf_k: int,
        min_vector_score: float,
    ) -> None:
        self._embedder = embedder
        self._aliases = aliases
        self._reranker = reranker
        self._candidate_k = candidate_k
        self._rrf_k = rrf_k
        self._min_vector_score = min_vector_score

    def search(
        self,
        snapshot: Snapshot,
        *,
        query: str,
        query_original: str | None,
        top_k: int,
        filters: SearchFilters,
        mode: Mode,
    ) -> list[Hit]:
        allowed = snapshot.allowed(filters)
        if allowed is not None and len(allowed) == 0:
            return []

        bm25_hits: list[tuple[int, float]] = []
        vector_hits: list[tuple[int, float]] = []
        if mode in ("hybrid", "bm25"):
            names = self._aliases.expand(query, query_original)
            tokens = tokenize(" ".join([query, *names]))
            bm25_hits = snapshot.bm25_top(tokens, allowed, self._candidate_k)
        if mode in ("hybrid", "vector"):
            vector = self._embedder.encode([query])[0]
            vector_hits = snapshot.vector_top(
                vector, allowed, self._candidate_k, self._min_vector_score
            )

        if mode == "hybrid":
            fused = rrf([[p for p, _ in bm25_hits], [p for p, _ in vector_hits]], self._rrf_k)
        else:
            fused = bm25_hits if mode == "bm25" else vector_hits
        bm25_scores = dict(bm25_hits)
        vector_scores = dict(vector_hits)
        hits = [
            Hit(p, s, bm25_scores.get(p), vector_scores.get(p))
            for p, s in fused[: self._candidate_k]
        ]
        return self._rerank(snapshot, query, hits)[:top_k]

    def _rerank(self, snapshot: Snapshot, query: str, hits: list[Hit]) -> list[Hit]:
        if self._reranker is None or not hits:
            return hits
        texts = [snapshot.records[h.position].chunk.text for h in hits]
        try:
            scores = self._reranker.score(query, texts)
        except Exception as exc:  # a search must not fail because the reranker did
            log.warning("rerank_failed", error_type=type(exc).__name__)
            return hits
        reranked = [replace(h, rerank_score=float(s)) for h, s in zip(hits, scores, strict=True)]
        return sorted(reranked, key=lambda h: -(h.rerank_score or 0.0))
