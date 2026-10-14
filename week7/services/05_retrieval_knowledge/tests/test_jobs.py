"""Rebuild jobs: one at a time, status kept in memory for the latest jobs."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.core.errors import AppError, ErrorCode
from app.index.jobs import RebuildJobs
from app.index.service import IndexService
from app.kb.store import KnowledgeStore
from tests.fakes import FakeEmbedder, GatedEmbedder
from tests.samples import SAMPLE_CHUNK_COUNT, SAMPLE_DOCUMENTS


@pytest.fixture
def store(tmp_path: Path) -> Iterator[KnowledgeStore]:
    s = KnowledgeStore(str(tmp_path / "kb.sqlite"))
    yield s
    s.close()


async def ready_index(store: KnowledgeStore, embedder: FakeEmbedder) -> IndexService:
    index = IndexService(store, embedder)
    await index.upsert(SAMPLE_DOCUMENTS)
    return index


async def test_a_job_goes_from_queued_to_done(store: KnowledgeStore) -> None:
    jobs = RebuildJobs(await ready_index(store, FakeEmbedder()))
    job = jobs.start(None)
    assert job.status == "queued"
    assert (job.started_at, job.finished_at, job.detail) == (None, None, None)
    await jobs.wait()
    done = jobs.get(job.job_id)
    assert done is job
    assert job.status == "done"
    assert job.started_at is not None
    assert job.finished_at is not None
    assert job.detail == f"6 documents, {SAMPLE_CHUNK_COUNT} chunks"


async def test_a_second_rebuild_while_one_runs_is_refused(store: KnowledgeStore) -> None:
    embedder = GatedEmbedder()
    jobs = RebuildJobs(await ready_index(store, embedder))
    embedder.hold_next = True
    job = jobs.start(None)
    await asyncio.to_thread(embedder.entered.wait, 10)
    assert job.status == "running"
    with pytest.raises(AppError) as refused:
        jobs.start("trivia")
    assert refused.value.code == ErrorCode.JOB_ALREADY_RUNNING
    embedder.release.set()
    await jobs.wait()
    assert jobs.start(None).status == "queued"  # free again once finished
    await jobs.wait()


async def test_a_failed_rebuild_is_reported_without_internals(store: KnowledgeStore) -> None:
    embedder = FakeEmbedder()
    jobs = RebuildJobs(await ready_index(store, embedder))
    embedder.fail = True
    job = jobs.start(None)
    await jobs.wait()
    assert job.status == "failed"
    assert job.detail == "RuntimeError"
    assert job.finished_at is not None


async def test_only_the_latest_jobs_are_kept(store: KnowledgeStore) -> None:
    jobs = RebuildJobs(await ready_index(store, FakeEmbedder()), keep=2)
    ids = []
    for _ in range(3):
        ids.append(jobs.start("match_report").job_id)
        await jobs.wait()
    assert jobs.get(ids[0]) is None
    assert jobs.get(ids[1]) is not None
    assert jobs.get(ids[2]) is not None


async def test_close_cancels_a_running_rebuild(store: KnowledgeStore) -> None:
    embedder = GatedEmbedder()
    index = await ready_index(store, embedder)
    before = index.snapshot
    jobs = RebuildJobs(index)
    embedder.hold_next = True
    job = jobs.start(None)
    await asyncio.to_thread(embedder.entered.wait, 10)
    embedder.release.set()
    await jobs.close()
    assert index.snapshot is before
    assert (job.status, job.detail) == ("failed", "cancelled")


async def test_shutdown_while_a_rebuild_writes_sqlite_waits_for_it(
    store: KnowledgeStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The app shuts down as main.py does: cancel the job, drain the index, close the store.
    # The worker already writing SQLite must finish first, and the snapshot must follow it.
    index = await ready_index(store, FakeEmbedder())
    entered, release = threading.Event(), threading.Event()
    write = store.replace_documents

    def slow_write(*args: Any, **kwargs: Any) -> None:
        entered.set()
        release.wait(10)
        write(*args, **kwargs)

    monkeypatch.setattr(store, "replace_documents", slow_write)
    jobs = RebuildJobs(index)
    jobs.start(None)
    await asyncio.to_thread(entered.wait, 10)
    await jobs.close()
    drained = asyncio.create_task(index.drain())
    await asyncio.sleep(0.05)
    assert not drained.done()  # the worker still holds the store: it must stay open
    release.set()
    await drained
    store.close()  # nothing uses the connection any more
    assert index.snapshot is not None
    reopened = KnowledgeStore(str(tmp_path / "kb.sqlite"))
    assert index.snapshot.index_version == reopened.get_meta("index_version")
    assert len(reopened.load_all()) == index.snapshot.size == SAMPLE_CHUNK_COUNT
    reopened.close()
