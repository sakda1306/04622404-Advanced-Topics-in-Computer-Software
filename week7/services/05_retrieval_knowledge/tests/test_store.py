"""SQLite store: one transaction per write, embeddings kept as float32."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from app.kb.chunking import chunk_document
from app.kb.documents import Chunk, Document
from app.kb.store import META_VERSION, KnowledgeStore
from tests.samples import MATCH, SAMPLE_CHUNK_COUNT, SAMPLE_DOCUMENTS

DIM = 4


def write(
    store: KnowledgeStore, documents: list[Document], version: str = "v1"
) -> tuple[dict[str, list[Chunk]], dict[str, np.ndarray]]:
    chunks = {d.doc_id: chunk_document(d) for d in documents}
    flat = [c for d in documents for c in chunks[d.doc_id]]
    embeddings = {c.chunk_id: np.full(DIM, float(i), dtype=np.float32) for i, c in enumerate(flat)}
    store.replace_documents(
        documents,
        chunks,
        embeddings,
        updated_at="2026-09-25T10:00:00.000+07:00",
        meta={META_VERSION: version},
    )
    return chunks, embeddings


@pytest.fixture
def store(tmp_path: Path) -> Iterator[KnowledgeStore]:
    s = KnowledgeStore(str(tmp_path / "kb.sqlite"))
    yield s
    s.close()


def test_round_trip(store: KnowledgeStore) -> None:
    _, embeddings = write(store, SAMPLE_DOCUMENTS)
    loaded = {s.chunk.chunk_id: s for s in store.load_all()}
    assert len(loaded) == SAMPLE_CHUNK_COUNT
    stored = loaded["match-2026-mw05-57-61#c1"]
    assert stored.document == MATCH
    assert stored.chunk.ord == 1
    np.testing.assert_array_equal(stored.embedding, embeddings["match-2026-mw05-57-61#c1"])
    assert stored.embedding.dtype == np.float32
    assert store.get_meta(META_VERSION) == "v1"


def test_hashes_of_known_documents_only(store: KnowledgeStore) -> None:
    write(store, SAMPLE_DOCUMENTS)
    doc = SAMPLE_DOCUMENTS[0]
    assert store.get_hashes([doc.doc_id, "trivia-9999"]) == {doc.doc_id: doc.content_hash()}


def test_hashes_for_more_ids_than_sqlite_parameters(store: KnowledgeStore) -> None:
    write(store, SAMPLE_DOCUMENTS)
    ids = [f"trivia-{i:04d}" for i in range(1, 1200)]
    assert set(store.get_hashes(ids)) == {"trivia-0001", "trivia-0002", "trivia-0003"}


def test_replacing_a_document_drops_its_old_chunks(store: KnowledgeStore) -> None:
    write(store, SAMPLE_DOCUMENTS)
    write(store, [replace(MATCH, text="Arsenal 2-1 Chelsea.")], version="v2")
    ids = [s.chunk.chunk_id for s in store.load_all() if s.chunk.doc_id == MATCH.doc_id]
    assert ids == ["match-2026-mw05-57-61#c0"]
    assert store.get_meta(META_VERSION) == "v2"


def test_failed_write_changes_nothing(store: KnowledgeStore) -> None:
    write(store, SAMPLE_DOCUMENTS)
    changed = replace(SAMPLE_DOCUMENTS[0], text="Q: changed?\nA: x")
    with pytest.raises(KeyError):
        # No embedding for the new chunk: fails after the old rows were deleted.
        store.replace_documents(
            [changed],
            {changed.doc_id: chunk_document(changed)},
            {},
            updated_at="later",
            meta={META_VERSION: "v2"},
        )
    original = SAMPLE_DOCUMENTS[0]
    assert store.get_hashes([original.doc_id]) == {original.doc_id: original.content_hash()}
    assert store.get_meta(META_VERSION) == "v1"
    assert len(store.load_all()) == SAMPLE_CHUNK_COUNT


def test_delete_removes_the_document_and_its_chunks(store: KnowledgeStore) -> None:
    write(store, SAMPLE_DOCUMENTS)
    assert store.delete_document(MATCH.doc_id, meta={META_VERSION: "v2"}) is True
    assert MATCH.doc_id not in {s.chunk.doc_id for s in store.load_all()}
    assert len(store.load_all()) == SAMPLE_CHUNK_COUNT - 2
    assert store.get_meta(META_VERSION) == "v2"


def test_deleting_an_unknown_document_changes_nothing(store: KnowledgeStore) -> None:
    write(store, SAMPLE_DOCUMENTS)
    assert store.delete_document("match-2026-mw05-1-2", meta={META_VERSION: "v2"}) is False
    assert len(store.load_all()) == SAMPLE_CHUNK_COUNT
    assert store.get_meta(META_VERSION) == "v1"


def test_load_documents_all_or_one_category(store: KnowledgeStore) -> None:
    write(store, SAMPLE_DOCUMENTS)
    assert store.load_documents() == sorted(SAMPLE_DOCUMENTS, key=lambda d: d.doc_id)
    assert store.load_documents("match_report") == [MATCH]
    assert store.load_documents("weekly_report") == []


def test_data_survives_reopening(tmp_path: Path) -> None:
    path = str(tmp_path / "kb.sqlite")
    first = KnowledgeStore(path)
    write(first, SAMPLE_DOCUMENTS)
    first.close()
    second = KnowledgeStore(path)
    assert len(second.load_all()) == SAMPLE_CHUNK_COUNT
    second.close()


def test_update_embeddings(store: KnowledgeStore) -> None:
    write(store, SAMPLE_DOCUMENTS)
    store.update_embeddings(
        {"trivia-0001#c0": np.ones(DIM, dtype=np.float32)}, meta={"embedding_model": "m2"}
    )
    loaded = {s.chunk.chunk_id: s for s in store.load_all()}
    np.testing.assert_array_equal(loaded["trivia-0001#c0"].embedding, np.ones(DIM))
    assert store.get_meta("embedding_model") == "m2"
