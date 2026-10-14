"""The real multilingual model on real trivia (run with: pytest -m model)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.core.config import RECOMMENDED_RERANK_MODEL
from app.index.service import IndexService
from app.kb.store import KnowledgeStore
from app.kb.trivia import load_trivia_documents
from app.search.aliases import AliasIndex
from app.search.embedder import SentenceTransformerEmbedder
from app.search.hybrid import Searcher
from app.search.reranker import load_reranker
from app.search.snapshot import SearchFilters

pytestmark = pytest.mark.model

TRIVIA_FILE = Path(__file__).parents[1] / "data" / "football_trivia_qa.txt"


@pytest.fixture(scope="module")
def real_embedder() -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder("paraphrase-multilingual-MiniLM-L12-v2")


def test_vectors_are_384_wide_and_normalised(real_embedder: SentenceTransformerEmbedder) -> None:
    vectors = real_embedder.encode(["Arsenal beat Chelsea", "ปืนใหญ่ชนะสิงห์บลู"])
    assert vectors.shape == (2, 384)
    assert vectors.dtype == np.float32
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


@pytest.mark.parametrize("mode", ["hybrid", "bm25", "vector"])
async def test_a_trivia_question_finds_its_own_entry(
    tmp_path: Path, real_embedder: SentenceTransformerEmbedder, mode: str
) -> None:
    documents, _ = load_trivia_documents(TRIVIA_FILE)
    store = KnowledgeStore(str(tmp_path / "kb.sqlite"))
    index = IndexService(store, real_embedder)
    await index.upsert(documents[:300])
    snapshot = index.snapshot
    assert snapshot is not None
    searcher = Searcher(
        real_embedder,
        AliasIndex([]),
        reranker=None,
        candidate_k=20,
        rrf_k=60,
        min_vector_score=0.0,
    )
    question = documents[0].title  # "It is alleged that this country 'sold out' ..."
    hits = searcher.search(
        snapshot,
        query=question,
        query_original=None,
        top_k=5,
        filters=SearchFilters(),
        mode=mode,  # type: ignore[arg-type]
    )
    assert snapshot.records[hits[0].position].chunk.doc_id == "trivia-0001"
    store.close()


async def test_the_recommended_reranker_keeps_the_right_entry_first(
    tmp_path: Path, real_embedder: SentenceTransformerEmbedder
) -> None:
    documents, _ = load_trivia_documents(TRIVIA_FILE)
    store = KnowledgeStore(str(tmp_path / "kb.sqlite"))
    index = IndexService(store, real_embedder)
    await index.upsert(documents[:300])
    snapshot = index.snapshot
    assert snapshot is not None
    reranker = load_reranker(RECOMMENDED_RERANK_MODEL)
    assert reranker is not None
    searcher = Searcher(
        real_embedder,
        AliasIndex([]),
        reranker=reranker,
        candidate_k=20,
        rrf_k=60,
        min_vector_score=0.0,
    )
    hits = searcher.search(
        snapshot,
        query=documents[0].title,
        query_original=None,
        top_k=5,
        filters=SearchFilters(),
        mode="hybrid",
    )
    assert snapshot.records[hits[0].position].chunk.doc_id == "trivia-0001"
    assert hits[0].rerank_score is not None
    store.close()
