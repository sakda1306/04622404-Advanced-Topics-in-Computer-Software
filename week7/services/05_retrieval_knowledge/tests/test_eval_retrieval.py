"""The retrieval eval: golden files that fit the knowledge base, metrics, a full run."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from app.kb.documents import doc_id_matches
from app.kb.store import KnowledgeStore
from app.kb.trivia import load_trivia_documents
from app.search.aliases import load_alias_file
from app.search.hybrid import Searcher
from scripts.eval_retrieval import (
    EVAL_DIR,
    Outcome,
    Query,
    abstention,
    answered_anyway,
    copy_knowledge_base,
    evaluate,
    first_rank,
    load_live_documents,
    load_queries,
    percentile,
    prepare_index,
    summarize,
    sweep_min_vector_score,
)
from tests.conftest import TEST_DATA
from tests.fakes import FakeEmbedder
from tests.samples import SAMPLE_DOCUMENTS
from tests.test_store import write

TRIVIA_FILE = Path(__file__).parents[1] / "data" / "football_trivia_qa.txt"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[KnowledgeStore]:
    s = KnowledgeStore(str(tmp_path / "kb.sqlite"))
    yield s
    s.close()


def test_first_rank_counts_documents_not_chunks() -> None:
    # Two chunks of the same document take one rank.
    assert first_rank(["a", "a", "b", "c"], frozenset({"c"})) == 3
    assert first_rank(["a", "b"], frozenset({"x"})) is None


def test_summary_metrics() -> None:
    q = Query("match", "match", "gm01", "q", None, {}, frozenset({"d"}))
    outcomes = [
        Outcome(q, "hybrid", 1, 10.0),
        Outcome(q, "hybrid", 3, 20.0),
        Outcome(q, "hybrid", None, 30.0),
        Outcome(q, "hybrid", 6, 40.0),
    ]
    [row] = summarize(outcomes)
    assert (row["set"], row["variant"], row["mode"], row["n"]) == ("match", "match", "hybrid", 4)
    assert row["hit@1"] == 0.25
    assert row["hit@5"] == 0.5
    assert row["mrr"] == pytest.approx((1 + 1 / 3 + 0 + 1 / 6) / 4)
    assert row["p50_ms"] == 25.0


def test_percentile() -> None:
    assert percentile([10.0, 20.0, 30.0, 40.0], 95) == pytest.approx(38.5)
    assert percentile([5.0], 50) == 5.0


def test_golden_files_fit_the_knowledge_base() -> None:
    trivia_ids = {d.doc_id for d in load_trivia_documents(str(TRIVIA_FILE))[0]}
    live = load_live_documents(EVAL_DIR)
    live_ids = {d.doc_id for d in live}
    assert all(doc_id_matches(d.category, d.doc_id) for d in live)
    queries = load_queries(EVAL_DIR)
    by_set: dict[str, list[Query]] = {}
    for query in queries:
        by_set.setdefault(query.set, []).append(query)
    assert len({q.id for q in by_set["trivia"]}) == 60
    assert len(by_set["match"]) == 20
    assert len(by_set["out_of_kb"]) == 20
    kinds = [q.variant for q in by_set["out_of_kb"]]
    assert kinds.count("football") == 10
    assert kinds.count("other") == 10
    for query in by_set["trivia"]:
        assert query.expected <= trivia_ids
    for query in by_set["match"]:
        assert query.expected and query.expected <= live_ids
    assert all(not q.expected for q in by_set["out_of_kb"])


def test_the_live_fixture_is_marked_synthetic() -> None:
    data = json.loads((EVAL_DIR / "fixtures" / "live_docs.json").read_text(encoding="utf-8"))
    assert data["synthetic"] is True


async def test_a_full_run_on_a_small_knowledge_base(store: KnowledgeStore) -> None:
    embedder = FakeEmbedder()
    index = await prepare_index(
        store, embedder, [*SAMPLE_DOCUMENTS, *load_live_documents(EVAL_DIR)]
    )
    snapshot = index.snapshot
    assert snapshot is not None
    searcher = Searcher(
        embedder,
        load_alias_file(str(TEST_DATA / "team_aliases.json")),
        reranker=None,
        candidate_k=20,
        rrf_k=60,
        min_vector_score=0.0,
    )
    queries = [q for q in load_queries(EVAL_DIR) if q.set in ("match", "out_of_kb")]
    outcomes = evaluate(searcher, snapshot, queries, modes=("bm25", "hybrid"))
    rows = summarize(outcomes)
    assert {(r["set"], r["mode"]) for r in rows} == {("match", "bm25"), ("match", "hybrid")}
    hybrid = next(r for r in rows if r["mode"] == "hybrid")
    assert hybrid["n"] == 20
    assert hybrid["hit@5"] >= 0.8  # the filters alone narrow most questions to their document

    sweep = sweep_min_vector_score(searcher, embedder, snapshot, queries, [0.0, 0.5, 1.01])
    assert [s["threshold"] for s in sweep] == [0.0, 0.5, 1.01]
    assert sweep[0]["in_kb_lost"] == 0.0
    # Football questions routed with a matchweek nothing was ingested for: empty at any cut-off.
    assert sweep[0]["out_of_kb_empty_hybrid"] > 0.0
    assert sweep[-1]["out_of_kb_empty_vector"] == 1.0
    assert 0.0 <= sweep[-1]["out_of_kb_empty_hybrid"] <= 1.0


def test_copy_includes_writes_still_in_the_wal(tmp_path: Path) -> None:
    # The service keeps its store open in WAL mode: recent writes are not in kb.sqlite yet.
    source = tmp_path / "kb.sqlite"
    store = KnowledgeStore(str(source))
    write(store, SAMPLE_DOCUMENTS)
    assert (tmp_path / "kb.sqlite-wal").stat().st_size > 0
    plain = tmp_path / "plain.sqlite"
    shutil.copyfile(source, plain)
    copied = tmp_path / "copy.sqlite"
    copy_knowledge_base(source, copied)
    store.close()

    def count(path: Path) -> int:
        with closing(sqlite3.connect(path)) as conn:
            try:
                return int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
            except sqlite3.DatabaseError:
                return 0

    assert count(plain) < len(SAMPLE_DOCUMENTS)  # why a file copy is not enough
    assert count(copied) == len(SAMPLE_DOCUMENTS)


def outcome(expected: bool, rank: int | None, top: float | None, kind: str = "football") -> Outcome:
    q = Query(
        "match" if expected else "out_of_kb",
        "match" if expected else kind,
        "q",
        "q",
        None,
        {},
        frozenset({"d"}) if expected else frozenset(),
    )
    return Outcome(q, "hybrid", rank, 1.0, 0 if top is None else 3, top)


def test_abstention_by_top_rerank_score() -> None:
    outcomes = [
        outcome(True, 1, 5.0),
        outcome(True, 2, -1.0),
        outcome(False, None, 3.0),
        outcome(False, None, None),  # filters left nothing: already refused
        outcome(False, None, -9.0, kind="other"),
    ]
    [low, high] = abstention(outcomes, [-8.0, 0.0], "hybrid+rerank:x")
    assert low == {
        "mode": "hybrid+rerank:x",
        "threshold": -8.0,
        "answerable_refused": 0.0,
        "answerable_kept_right": 0.5,
        "unanswerable_answered_football": 0.5,
        "unanswerable_answered_other": 0.0,
    }
    assert high["answerable_refused"] == 0.5
    assert high["unanswerable_answered_football"] == 0.5


def test_answered_anyway_counts_unanswerable_questions_with_chunks() -> None:
    rows = answered_anyway([outcome(False, None, 3.0), outcome(False, None, None)])
    assert rows == [{"kind": "football", "mode": "hybrid", "n": 2, "returned_chunks": 0.5}]
