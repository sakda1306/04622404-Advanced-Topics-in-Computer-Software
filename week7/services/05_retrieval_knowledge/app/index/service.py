"""Writes to the Knowledge Base (CONTRACT §6): one writer at a time, readers never wait.

An upsert is all or nothing: chunks are embedded and the new snapshot is built before
anything is written, the store is written in one transaction, and only then is the new
snapshot swapped in. If any step fails, the store and the snapshot that searches use are
both unchanged. A delete follows the same order.

A rebuild re-chunks and re-embeds stored documents in two steps, so writes do not wait
for the slow part: it embeds everything without the lock, then takes the lock, re-reads
the store and embeds only the text that changed in the meantime before swapping.

Once a write has started it runs to the end even if its caller is cancelled (shutdown,
a dropped request): the worker thread cannot be stopped halfway, so stopping only the
coroutine could leave SQLite written and the snapshot not swapped. `drain()` waits for
such writes; the app calls it before closing the store.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

import numpy as np

from app.core.clock import bangkok_now, version_stamp
from app.core.logging import get_logger
from app.kb.chunking import chunk_document
from app.kb.documents import Chunk, Document
from app.kb.store import META_MODEL, META_VERSION, KnowledgeStore, StoredChunk
from app.search.embedder import Embedder
from app.search.snapshot import IndexedChunk, Snapshot
from app.search.tokenize import tokenize

log = get_logger(__name__)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class UpsertResult:
    upserted: int
    chunks: int
    index_version: str | None


@dataclass(frozen=True, slots=True)
class RebuildResult:
    documents: int
    chunks: int
    index_version: str | None


@dataclass(frozen=True, slots=True)
class IndexStats:
    documents: int
    chunks: int
    by_category: dict[str, int]  # documents per category
    index_version: str | None


def index_stats(snapshot: Snapshot) -> IndexStats:
    """Counts from the snapshot, which holds the same chunks as the store (CONTRACT §6)."""
    documents = {r.document.doc_id: r.document.category for r in snapshot.records}
    return IndexStats(
        documents=len(documents),
        chunks=snapshot.size,
        by_category=dict(Counter(documents.values())),
        index_version=snapshot.index_version,
    )


def _indexed(chunk: Chunk, document: Document, embedding: np.ndarray) -> IndexedChunk:
    return IndexedChunk(chunk, document, embedding, tuple(tokenize(chunk.bm25_text)))


class IndexService:
    def __init__(
        self,
        store: KnowledgeStore,
        embedder: Embedder,
        *,
        clock: Callable[[], datetime] = bangkok_now,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._clock = clock
        self._lock = asyncio.Lock()
        self._snapshot: Snapshot | None = None
        self._running: set[asyncio.Task[object]] = set()

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snapshot

    async def drain(self) -> None:
        """Wait for loads and writes already started; call before closing the store."""
        while self._running:
            await asyncio.gather(*self._running, return_exceptions=True)

    async def _to_the_end(self, work: Awaitable[T]) -> T:
        task: asyncio.Task[T] = asyncio.ensure_future(work)
        self._running.add(task)  # type: ignore[arg-type]
        task.add_done_callback(self._running.discard)  # type: ignore[arg-type]
        return await asyncio.shield(task)

    async def load(self) -> None:
        await self._to_the_end(self._load())

    async def upsert(self, documents: Sequence[Document]) -> UpsertResult:
        return await self._to_the_end(self._upsert(documents))

    async def delete(self, doc_id: str) -> bool:
        """Remove a document; False, with nothing changed, when it is not in the index."""
        return await self._to_the_end(self._delete(doc_id))

    async def _load(self) -> None:
        async with self._lock:
            self._snapshot = await asyncio.to_thread(self._load_sync)

    async def _upsert(self, documents: Sequence[Document]) -> UpsertResult:
        async with self._lock:
            current = self._snapshot or await asyncio.to_thread(self._load_sync)
            snapshot, result = await asyncio.to_thread(self._upsert_sync, current, documents)
            self._snapshot = snapshot
            return result

    async def _delete(self, doc_id: str) -> bool:
        async with self._lock:
            current = self._snapshot or await asyncio.to_thread(self._load_sync)
            snapshot = await asyncio.to_thread(self._delete_sync, current, doc_id)
            self._snapshot = snapshot or current
            return snapshot is not None

    async def rebuild(self, category: str | None = None) -> RebuildResult:
        """Re-chunk and re-embed the stored documents of one category, or of all of them."""
        # Step 1, no lock: the slow embedding; searches and writes go on meanwhile.
        # Cancelling here is safe; the read that uses the store is still waited for.
        documents = await self._to_the_end(asyncio.to_thread(self._store.load_documents, category))
        embedded = await asyncio.to_thread(self._embed_texts, documents, {})
        # Step 2, locked: pick up what was written during step 1, then swap. It writes
        # SQLite, so once started it runs to the end like any other write.
        return await self._to_the_end(self._rebuild(category, embedded))

    async def _rebuild(
        self, category: str | None, embedded: dict[str, np.ndarray]
    ) -> RebuildResult:
        async with self._lock:
            current = self._snapshot or await asyncio.to_thread(self._load_sync)
            snapshot, result = await asyncio.to_thread(
                self._rebuild_sync, current, category, embedded
            )
            self._snapshot = snapshot
            return result

    def _embed_texts(
        self, documents: Sequence[Document], known: dict[str, np.ndarray]
    ) -> dict[str, np.ndarray]:
        """Vectors by chunk text; texts already in `known` are not embedded again."""
        texts = {c.text for d in documents for c in chunk_document(d)} - known.keys()
        ordered = sorted(texts)
        vectors = self._embedder.encode(ordered) if ordered else []
        return {**known, **dict(zip(ordered, vectors, strict=True))}

    def _load_sync(self) -> Snapshot:
        stored = self._store.load_all()
        if stored and self._store.get_meta(META_MODEL) != self._embedder.model_name:
            stored = self._reembed(stored)
        records = [_indexed(s.chunk, s.document, s.embedding) for s in stored]
        return Snapshot(
            records,
            dimension=self._embedder.dimension,
            index_version=self._store.get_meta(META_VERSION),
        )

    def _reembed(self, stored: list[StoredChunk]) -> list[StoredChunk]:
        # Vectors from another model are not comparable with the new query vectors.
        log.info("reembedding_all_chunks", chunks=len(stored), model=self._embedder.model_name)
        vectors = self._embedder.encode([s.chunk.text for s in stored])
        embeddings = {s.chunk.chunk_id: v for s, v in zip(stored, vectors, strict=True)}
        self._store.update_embeddings(embeddings, meta={META_MODEL: self._embedder.model_name})
        return [StoredChunk(s.chunk, s.document, embeddings[s.chunk.chunk_id]) for s in stored]

    def _upsert_sync(
        self, current: Snapshot, documents: Sequence[Document]
    ) -> tuple[Snapshot, UpsertResult]:
        latest = {d.doc_id: d for d in documents}  # the last copy of a doc_id wins
        stored_hashes = self._store.get_hashes(latest)
        changed = [d for d in latest.values() if stored_hashes.get(d.doc_id) != d.content_hash()]
        existing = Counter(r.chunk.doc_id for r in current.records)
        if not changed:
            total = sum(existing[doc_id] for doc_id in latest)
            return current, UpsertResult(len(latest), total, current.index_version)

        chunks = {d.doc_id: chunk_document(d) for d in changed}
        flat = [c for d in changed for c in chunks[d.doc_id]]
        vectors = self._embedder.encode([c.text for c in flat])  # before anything is written
        embeddings = {c.chunk_id: v for c, v in zip(flat, vectors, strict=True)}
        version = version_stamp(self._clock())
        by_id = {d.doc_id: d for d in changed}
        records = [r for r in current.records if r.chunk.doc_id not in by_id]
        records += [_indexed(c, by_id[c.doc_id], embeddings[c.chunk_id]) for c in flat]
        # Built before the write: if it fails, the store never sees the change.
        snapshot = Snapshot(records, dimension=self._embedder.dimension, index_version=version)
        self._store.replace_documents(
            changed,
            chunks,
            embeddings,
            updated_at=version,
            meta={META_VERSION: version, META_MODEL: self._embedder.model_name},
        )

        total = sum(
            len(chunks[doc_id]) if doc_id in chunks else existing[doc_id] for doc_id in latest
        )
        log.info("index_updated", documents=len(changed), chunks=len(flat), index_version=version)
        return snapshot, UpsertResult(len(latest), total, version)

    def _delete_sync(self, current: Snapshot, doc_id: str) -> Snapshot | None:
        records = [r for r in current.records if r.chunk.doc_id != doc_id]
        if len(records) == len(current.records):
            return None
        version = version_stamp(self._clock())
        # Built before the write: if it fails, the store never sees the change.
        snapshot = Snapshot(records, dimension=self._embedder.dimension, index_version=version)
        self._store.delete_document(doc_id, meta={META_VERSION: version})
        log.info("index_document_deleted", doc_id=doc_id, index_version=version)
        return snapshot

    def _rebuild_sync(
        self, current: Snapshot, category: str | None, embedded: dict[str, np.ndarray]
    ) -> tuple[Snapshot, RebuildResult]:
        documents = self._store.load_documents(category)
        embedded = self._embed_texts(documents, embedded)
        chunks = {d.doc_id: chunk_document(d) for d in documents}
        flat = [c for d in documents for c in chunks[d.doc_id]]
        embeddings = {c.chunk_id: embedded[c.text] for c in flat}
        version = version_stamp(self._clock())
        by_id = {d.doc_id: d for d in documents}
        records = [
            r for r in current.records if category is not None and r.document.category != category
        ]
        records += [_indexed(c, by_id[c.doc_id], embeddings[c.chunk_id]) for c in flat]
        # Built before the write: if it fails, the store never sees the change.
        snapshot = Snapshot(records, dimension=self._embedder.dimension, index_version=version)
        self._store.replace_documents(
            documents,
            chunks,
            embeddings,
            updated_at=version,
            meta={META_VERSION: version, META_MODEL: self._embedder.model_name},
        )
        log.info(
            "index_rebuilt",
            category=category,
            documents=len(documents),
            chunks=len(flat),
            index_version=version,
        )
        return snapshot, RebuildResult(len(documents), len(flat), version)
