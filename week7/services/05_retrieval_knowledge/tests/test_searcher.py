"""Search modes, RRF, nickname expansion and reranking (CONTRACT §4)."""

from __future__ import annotations

import pytest

from app.search.aliases import AliasIndex, load_alias_file
from app.search.hybrid import Hit, Mode, Searcher, rrf
from app.search.reranker import Reranker
from app.search.snapshot import SearchFilters, Snapshot
from tests.conftest import TEST_DATA
from tests.fakes import FailingReranker, FakeEmbedder, FakeReranker
from tests.test_snapshot import build_snapshot

ALIASES = load_alias_file(str(TEST_DATA / "team_aliases.json"))


def make(
    *,
    aliases: AliasIndex = ALIASES,
    reranker: Reranker | None = None,
    min_vector_score: float = 0.0,
) -> tuple[Searcher, Snapshot, FakeEmbedder]:
    snapshot, embedder = build_snapshot()
    searcher = Searcher(
        embedder,
        aliases,
        reranker=reranker,
        candidate_k=20,
        rrf_k=60,
        min_vector_score=min_vector_score,
    )
    return searcher, snapshot, embedder


def run(
    searcher: Searcher,
    snapshot: Snapshot,
    query: str,
    *,
    mode: Mode = "hybrid",
    query_original: str | None = None,
    top_k: int = 5,
    filters: SearchFilters | None = None,
) -> list[Hit]:
    return searcher.search(
        snapshot,
        query=query,
        query_original=query_original,
        top_k=top_k,
        filters=filters or SearchFilters(),
        mode=mode,
    )


def first_doc(snapshot: Snapshot, hits: list[Hit]) -> str:
    return snapshot.records[hits[0].position].chunk.doc_id


def test_rrf_rewards_chunks_found_by_both_lists() -> None:
    fused = rrf([[1, 2], [2, 3]], 60)
    assert fused[0] == (2, pytest.approx(1 / 62 + 1 / 61))
    assert [p for p, _ in fused] == [2, 1, 3]


def test_hybrid_uses_rrf_and_keeps_both_raw_scores() -> None:
    searcher, snapshot, _ = make()
    hits = run(searcher, snapshot, "Arsenal Chelsea result")
    assert first_doc(snapshot, hits) == "match-2026-mw05-57-61"
    top = hits[0]
    assert top.bm25_score is not None and top.vector_score is not None
    assert top.score < 1 / 30  # an RRF score, not a raw one


def test_bm25_mode_scores_are_raw_bm25() -> None:
    searcher, snapshot, _ = make()
    hits = run(searcher, snapshot, "Arsenal Chelsea", mode="bm25")
    assert hits and all(h.score == h.bm25_score and h.vector_score is None for h in hits)


def test_vector_mode_scores_are_cosine() -> None:
    searcher, snapshot, _ = make()
    hits = run(searcher, snapshot, "World Cup Spain", mode="vector")
    assert hits and all(h.score == h.vector_score and h.bm25_score is None for h in hits)
    assert first_doc(snapshot, hits) == "trivia-0003"


def test_thai_only_query_finds_match_through_alias() -> None:
    searcher, snapshot, _ = make()
    hits = run(searcher, snapshot, "ปืนใหญ่ชนะไหม", mode="bm25")
    assert hits
    assert snapshot.records[hits[0].position].document.team_ids[0] == 57


def test_without_aliases_the_thai_query_finds_nothing_in_bm25() -> None:
    searcher, snapshot, _ = make(aliases=AliasIndex([]))
    assert run(searcher, snapshot, "ปืนใหญ่ชนะไหม", mode="bm25") == []


def test_vector_side_embeds_the_english_query() -> None:
    # eval PR ③: the Thai original cost hybrid 0.70 -> 0.90 hit@1 on the match set.
    searcher, snapshot, embedder = make()
    run(searcher, snapshot, "Arsenal result", query_original="ปืนใหญ่ชนะไหม")
    assert embedder.calls[-1] == ["Arsenal result"]


def test_filters_limit_every_hit() -> None:
    searcher, snapshot, _ = make()
    hits = run(searcher, snapshot, "Arsenal", filters=SearchFilters(category=("standings",)))
    assert hits
    assert {snapshot.records[h.position].chunk.doc_id for h in hits} == {"standings-2026-mw05"}


def test_filter_with_no_chunks_returns_nothing_without_embedding() -> None:
    searcher, snapshot, embedder = make()
    calls = len(embedder.calls)
    assert run(searcher, snapshot, "Arsenal", filters=SearchFilters(season="1999")) == []
    assert len(embedder.calls) == calls


def test_query_without_tokens_does_not_crash() -> None:
    searcher, snapshot, _ = make()
    assert run(searcher, snapshot, "???", mode="bm25") == []
    assert isinstance(run(searcher, snapshot, "???"), list)


def test_top_k_cuts_the_list() -> None:
    searcher, snapshot, _ = make()
    assert len(run(searcher, snapshot, "Arsenal Liverpool Chelsea", top_k=2)) == 2


def test_min_vector_score_can_leave_the_answer_empty() -> None:
    searcher, snapshot, _ = make(min_vector_score=0.99)
    assert run(searcher, snapshot, "zzz qqq", mode="vector") == []


def test_reranker_reorders_and_sets_rerank_score() -> None:
    searcher, snapshot, _ = make(reranker=FakeReranker(prefer="Brian Deane"))
    hits = run(searcher, snapshot, "Premier League goal", top_k=3)
    assert first_doc(snapshot, hits) == "trivia-0002"
    assert hits[0].rerank_score == 1.0
    assert all(h.rerank_score is not None for h in hits)


def test_failing_reranker_falls_back_to_the_fused_order() -> None:
    plain, snapshot, _ = make()
    failing, _, _ = make(reranker=FailingReranker())
    expected = [h.position for h in run(plain, snapshot, "Arsenal Chelsea")]
    hits = run(failing, snapshot, "Arsenal Chelsea")
    assert [h.position for h in hits] == expected
    assert all(h.rerank_score is None for h in hits)
