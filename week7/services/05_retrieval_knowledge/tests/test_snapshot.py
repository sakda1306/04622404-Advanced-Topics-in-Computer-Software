"""Snapshot: FAISS and BM25 over the same chunks, filtered before ranking."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pytest

from app.kb.chunking import chunk_document
from app.kb.documents import Document
from app.search.snapshot import IndexedChunk, SearchFilters, Snapshot
from app.search.tokenize import tokenize
from tests.fakes import FakeEmbedder
from tests.samples import SAMPLE_CHUNK_COUNT, SAMPLE_DOCUMENTS


def build_snapshot(
    documents: list[Document] = SAMPLE_DOCUMENTS, version: str | None = "v1"
) -> tuple[Snapshot, FakeEmbedder]:
    embedder = FakeEmbedder()
    records = []
    for doc in documents:
        chunks = chunk_document(doc)
        vectors = embedder.encode([c.text for c in chunks])
        records += [
            IndexedChunk(c, doc, v, tuple(tokenize(c.bm25_text)))
            for c, v in zip(chunks, vectors, strict=True)
        ]
    return Snapshot(records, dimension=embedder.dimension, index_version=version), embedder


def doc_ids(snapshot: Snapshot, positions: Iterable[int]) -> set[str]:
    return {snapshot.records[int(p)].chunk.doc_id for p in positions}


def test_faiss_and_bm25_hold_the_same_chunks() -> None:
    snapshot, _ = build_snapshot()
    assert snapshot.size == snapshot.faiss_count == snapshot.bm25_count == SAMPLE_CHUNK_COUNT
    assert snapshot.index_version == "v1"


def test_empty_snapshot_searches_to_nothing() -> None:
    snapshot = Snapshot([], dimension=64, index_version=None)
    assert snapshot.size == 0
    assert snapshot.bm25_top(["arsenal"], None, 5) == []
    assert snapshot.vector_top(np.ones(64, dtype=np.float32), None, 5, 0.0) == []


def test_no_filter_means_every_chunk() -> None:
    snapshot, _ = build_snapshot()
    assert SearchFilters().is_empty()
    assert snapshot.allowed(SearchFilters()) is None


def test_a_topic_filter_is_not_empty() -> None:
    assert not SearchFilters(topic=("club_record",)).is_empty()


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (SearchFilters(category=("match_report",)), {"match-2026-mw05-57-61"}),
        (
            SearchFilters(season="2026", matchweek=5),
            {"match-2026-mw05-57-61", "standings-2026-mw05"},
        ),
        (SearchFilters(team_ids=(64,)), {"standings-2026-mw05", "fixtures-2026-team-64"}),
        (
            SearchFilters(date_from="2026-09-21"),
            {"standings-2026-mw05", "fixtures-2026-team-64"},
        ),
        (SearchFilters(date_to="2026-09-20"), {"match-2026-mw05-57-61"}),
        (SearchFilters(category=("trivia",), season="2026"), set()),
        (SearchFilters(topic=("World Cup",)), {"trivia-0003"}),
        (SearchFilters(topic=("World Cup", "Ballon d'Or")), {"trivia-0001", "trivia-0003"}),
        (SearchFilters(topic=("World Cup",), team_ids=(57,)), set()),
    ],
)
def test_filters(filters: SearchFilters, expected: set[str]) -> None:
    snapshot, _ = build_snapshot()
    allowed = snapshot.allowed(filters)
    assert allowed is not None
    assert doc_ids(snapshot, allowed) == expected


def test_bm25_skips_zero_scores_and_respects_filters() -> None:
    snapshot, _ = build_snapshot()
    hits = snapshot.bm25_top(["chelsea"], None, 20)
    assert doc_ids(snapshot, [p for p, _ in hits]) == {"match-2026-mw05-57-61"}
    assert all(score > 0 for _, score in hits)
    standings_only = snapshot.allowed(SearchFilters(category=("standings",)))
    assert snapshot.bm25_top(["chelsea"], standings_only, 20) == []


def test_bm25_without_tokens_finds_nothing() -> None:
    snapshot, _ = build_snapshot()
    assert snapshot.bm25_top([], None, 20) == []


def test_vector_top_stays_inside_the_filter() -> None:
    snapshot, embedder = build_snapshot()
    allowed = snapshot.allowed(SearchFilters(category=("trivia",)))
    vector = embedder.encode(["Arsenal Chelsea"])[0]
    hits = snapshot.vector_top(vector, allowed, 20, 0.0)
    assert doc_ids(snapshot, [p for p, _ in hits]) <= {"trivia-0001", "trivia-0002", "trivia-0003"}


def test_vector_top_never_returns_missing_ids() -> None:
    # k far above the 3 chunks that pass the filter: FAISS pads with -1, which must not leak.
    snapshot, embedder = build_snapshot()
    allowed = snapshot.allowed(SearchFilters(category=("trivia",)))
    assert allowed is not None
    hits = snapshot.vector_top(embedder.encode(["World Cup"])[0], allowed, 20, 0.0)
    assert len(hits) == 3
    assert all(0 <= p < snapshot.size for p, _ in hits)


def test_vector_min_score_drops_weak_matches() -> None:
    snapshot, embedder = build_snapshot()
    text = snapshot.records[0].chunk.text
    hits = snapshot.vector_top(embedder.encode([text])[0], None, 20, 0.99)
    assert [p for p, _ in hits] == [0]
