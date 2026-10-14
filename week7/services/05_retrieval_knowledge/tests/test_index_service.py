"""Index writes: one writer at a time, all or nothing, snapshot swapped only on success."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import app.index.service as service_module
from app.core.clock import BANGKOK
from app.index.service import (
    IndexService,
    IndexStats,
    RebuildResult,
    UpsertResult,
    index_stats,
)
from app.kb.store import META_MODEL, KnowledgeStore
from tests.fakes import FakeEmbedder, GatedEmbedder
from tests.samples import FIXTURES, MATCH, SAMPLE_CHUNK_COUNT, SAMPLE_DOCUMENTS


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 25, 10, 0, tzinfo=BANGKOK)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def store(tmp_path: Path) -> Iterator[KnowledgeStore]:
    s = KnowledgeStore(str(tmp_path / "kb.sqlite"))
    yield s
    s.close()


def service(store: KnowledgeStore, embedder: FakeEmbedder | None = None) -> IndexService:
    return IndexService(store, embedder or FakeEmbedder(), clock=Clock())


async def test_empty_store_loads_an_empty_snapshot(store: KnowledgeStore) -> None:
    index = service(store)
    await index.load()
    assert index.snapshot is not None
    assert index.snapshot.size == 0
    assert index.snapshot.index_version is None


async def test_upsert_builds_a_snapshot_and_a_version(store: KnowledgeStore) -> None:
    index = service(store)
    result = await index.upsert(SAMPLE_DOCUMENTS)
    assert result == UpsertResult(6, SAMPLE_CHUNK_COUNT, "2026-09-25T10:00:01.000+07:00")
    snapshot = index.snapshot
    assert snapshot is not None
    assert snapshot.size == snapshot.faiss_count == snapshot.bm25_count == SAMPLE_CHUNK_COUNT
    assert snapshot.index_version == result.index_version


async def test_unchanged_upsert_does_not_embed_or_bump_version(store: KnowledgeStore) -> None:
    embedder = FakeEmbedder()
    index = service(store, embedder)
    first = await index.upsert(SAMPLE_DOCUMENTS)
    before, calls = index.snapshot, len(embedder.calls)
    again = await index.upsert(SAMPLE_DOCUMENTS)
    assert again == first
    assert len(embedder.calls) == calls
    assert index.snapshot is before


async def test_changed_document_replaces_its_chunks(store: KnowledgeStore) -> None:
    index = service(store)
    first = await index.upsert(SAMPLE_DOCUMENTS)
    result = await index.upsert([replace(MATCH, text="Arsenal 2-1 Chelsea.")])
    assert result.upserted == 1
    assert result.chunks == 1
    assert result.index_version != first.index_version
    snapshot = index.snapshot
    assert snapshot is not None
    assert snapshot.size == SAMPLE_CHUNK_COUNT - 1
    ids = [r.chunk.chunk_id for r in snapshot.records if r.chunk.doc_id == MATCH.doc_id]
    assert ids == ["match-2026-mw05-57-61#c0"]


async def test_last_copy_of_a_doc_id_wins(store: KnowledgeStore) -> None:
    index = service(store)
    result = await index.upsert([MATCH, replace(MATCH, text="Arsenal 2-1 Chelsea.")])
    assert (result.upserted, result.chunks) == (1, 1)


async def test_embedding_failure_changes_nothing(store: KnowledgeStore) -> None:
    embedder = FakeEmbedder()
    index = service(store, embedder)
    first = await index.upsert(SAMPLE_DOCUMENTS)
    before = index.snapshot
    embedder.fail = True
    with pytest.raises(RuntimeError):
        await index.upsert([replace(MATCH, text="changed")])
    assert index.snapshot is before
    assert store.get_hashes([MATCH.doc_id]) == {MATCH.doc_id: MATCH.content_hash()}
    assert store.get_meta("index_version") == first.index_version


async def test_store_failure_keeps_the_old_snapshot(
    store: KnowledgeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = service(store)
    await index.upsert(SAMPLE_DOCUMENTS)
    before = index.snapshot

    def broken(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "replace_documents", broken)
    with pytest.raises(sqlite3.OperationalError):
        await index.upsert([replace(MATCH, text="changed")])
    assert index.snapshot is before


async def test_snapshot_failure_leaves_the_store_unchanged(
    store: KnowledgeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = service(store)
    await index.upsert(SAMPLE_DOCUMENTS)
    before = index.snapshot
    changed = replace(MATCH, text="changed")

    def broken(*_args: object, **_kwargs: object) -> None:
        raise MemoryError("faiss")

    with monkeypatch.context() as m:
        m.setattr(service_module, "Snapshot", broken)
        with pytest.raises(MemoryError):
            await index.upsert([changed])
    assert index.snapshot is before
    stored = {s.document.doc_id: s.document.text for s in store.load_all()}
    assert stored[MATCH.doc_id] == MATCH.text

    # The store did not take the change, so a retry is not skipped as unchanged.
    await index.upsert([changed])
    assert index.snapshot is not None
    texts = {r.document.doc_id: r.document.text for r in index.snapshot.records}
    assert texts[MATCH.doc_id] == "changed"


async def test_delete_removes_a_document_from_store_and_snapshot(store: KnowledgeStore) -> None:
    index = service(store)
    first = await index.upsert(SAMPLE_DOCUMENTS)
    assert await index.delete(MATCH.doc_id) is True
    snapshot = index.snapshot
    assert snapshot is not None
    assert MATCH.doc_id not in {r.chunk.doc_id for r in snapshot.records}
    assert snapshot.size == snapshot.faiss_count == snapshot.bm25_count == SAMPLE_CHUNK_COUNT - 2
    assert snapshot.index_version != first.index_version
    assert store.get_meta("index_version") == snapshot.index_version
    assert len(store.load_all()) == SAMPLE_CHUNK_COUNT - 2


async def test_deleting_twice_is_false_and_keeps_the_version(store: KnowledgeStore) -> None:
    index = service(store)
    await index.upsert(SAMPLE_DOCUMENTS)
    await index.delete(MATCH.doc_id)
    before = index.snapshot
    assert await index.delete(MATCH.doc_id) is False
    assert index.snapshot is before


async def test_delete_failure_changes_nothing(
    store: KnowledgeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = service(store)
    await index.upsert(SAMPLE_DOCUMENTS)
    before = index.snapshot

    def broken(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "delete_document", broken)
    with pytest.raises(sqlite3.OperationalError):
        await index.delete(MATCH.doc_id)
    assert index.snapshot is before
    assert len(store.load_all()) == SAMPLE_CHUNK_COUNT


async def test_stats_count_documents_chunks_and_categories(store: KnowledgeStore) -> None:
    index = service(store)
    result = await index.upsert(SAMPLE_DOCUMENTS)
    assert index.snapshot is not None
    assert index_stats(index.snapshot) == IndexStats(
        documents=6,
        chunks=SAMPLE_CHUNK_COUNT,
        by_category={"trivia": 3, "match_report": 1, "standings": 1, "fixtures": 1},
        index_version=result.index_version,
    )


async def test_restart_reuses_stored_embeddings(store: KnowledgeStore) -> None:
    first = service(store)
    result = await first.upsert(SAMPLE_DOCUMENTS)
    embedder = FakeEmbedder()
    restarted = service(store, embedder)
    await restarted.load()
    assert restarted.snapshot is not None
    assert restarted.snapshot.size == SAMPLE_CHUNK_COUNT
    assert restarted.snapshot.index_version == result.index_version
    assert embedder.calls == []


async def test_new_embedding_model_reembeds_everything_once(store: KnowledgeStore) -> None:
    await service(store, FakeEmbedder("model-a")).upsert(SAMPLE_DOCUMENTS)
    model_b = FakeEmbedder("model-b")
    await service(store, model_b).load()
    assert [len(batch) for batch in model_b.calls] == [SAMPLE_CHUNK_COUNT]
    assert store.get_meta(META_MODEL) == "model-b"
    again = FakeEmbedder("model-b")
    await service(store, again).load()
    assert again.calls == []


def ids_in(index: IndexService) -> set[str]:
    assert index.snapshot is not None
    return {r.chunk.doc_id for r in index.snapshot.records}


async def test_rebuild_reembeds_everything_and_bumps_the_version(store: KnowledgeStore) -> None:
    embedder = FakeEmbedder()
    index = service(store, embedder)
    first = await index.upsert(SAMPLE_DOCUMENTS)
    result = await index.rebuild()
    assert result == RebuildResult(6, SAMPLE_CHUNK_COUNT, result.index_version)
    assert result.index_version != first.index_version
    assert len(embedder.calls[-1]) == SAMPLE_CHUNK_COUNT
    snapshot = index.snapshot
    assert snapshot is not None
    assert snapshot.size == snapshot.faiss_count == snapshot.bm25_count == SAMPLE_CHUNK_COUNT
    assert snapshot.index_version == store.get_meta("index_version") == result.index_version
    assert len(store.load_all()) == SAMPLE_CHUNK_COUNT


async def test_rebuild_of_one_category_embeds_only_that_category(store: KnowledgeStore) -> None:
    embedder = FakeEmbedder()
    index = service(store, embedder)
    await index.upsert(SAMPLE_DOCUMENTS)
    result = await index.rebuild("match_report")
    assert (result.documents, result.chunks) == (1, 2)
    assert [len(batch) for batch in embedder.calls[1:]] == [2]
    assert index.snapshot is not None
    assert index.snapshot.size == SAMPLE_CHUNK_COUNT


async def test_writes_during_a_rebuild_are_kept(store: KnowledgeStore) -> None:
    embedder = GatedEmbedder()
    index = service(store, embedder)
    await index.upsert(SAMPLE_DOCUMENTS)
    before = index.snapshot
    changed = replace(MATCH, text="Arsenal 3-1 Chelsea after a late goal.")

    embedder.hold_next = True
    task = asyncio.create_task(index.rebuild())
    await asyncio.to_thread(embedder.entered.wait, 10)
    # Mid-embedding: searches still see the old snapshot and writes do not wait.
    assert index.snapshot is before
    await index.upsert([changed])
    assert await index.delete(FIXTURES.doc_id) is True
    calls = len(embedder.calls)
    embedder.release.set()
    result = await task

    assert ids_in(index) == {d.doc_id for d in SAMPLE_DOCUMENTS} - {FIXTURES.doc_id}
    assert result.documents == 5
    assert index.snapshot is not None
    texts = {r.document.doc_id: r.document.text for r in index.snapshot.records}
    assert texts[MATCH.doc_id] == changed.text
    # Only the document written during the rebuild is embedded again, not the whole store.
    assert [len(batch) for batch in embedder.calls[calls + 1 :]] == [1]
    assert {s.chunk.doc_id for s in store.load_all()} == ids_in(index)


async def test_rebuild_failure_changes_nothing(store: KnowledgeStore) -> None:
    embedder = FakeEmbedder()
    index = service(store, embedder)
    first = await index.upsert(SAMPLE_DOCUMENTS)
    before = index.snapshot
    embedder.fail = True
    with pytest.raises(RuntimeError):
        await index.rebuild()
    assert index.snapshot is before
    assert store.get_meta("index_version") == first.index_version


async def test_a_started_write_finishes_even_if_its_caller_is_cancelled(
    store: KnowledgeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Shutdown cancels requests and jobs, but a worker thread cannot be stopped midway:
    # once SQLite is written the snapshot must be swapped too, or the two disagree.
    index = service(store)
    await index.upsert(SAMPLE_DOCUMENTS)
    entered, release = threading.Event(), threading.Event()
    write = store.replace_documents

    def slow_write(*args: Any, **kwargs: Any) -> None:
        entered.set()
        release.wait(10)
        write(*args, **kwargs)

    monkeypatch.setattr(store, "replace_documents", slow_write)
    caller = asyncio.create_task(index.upsert([replace(MATCH, text="Arsenal 3-1 Chelsea.")]))
    await asyncio.to_thread(entered.wait, 10)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    drained = asyncio.create_task(index.drain())
    await asyncio.sleep(0.05)
    assert not drained.done()  # still waiting for the worker: the store must stay open
    release.set()
    await drained
    assert index.snapshot is not None
    assert index.snapshot.index_version == store.get_meta("index_version")
    texts = {r.document.doc_id: r.document.text for r in index.snapshot.records}
    assert texts[MATCH.doc_id] == "Arsenal 3-1 Chelsea."


async def test_drain_with_nothing_running_returns(store: KnowledgeStore) -> None:
    await service(store).drain()
