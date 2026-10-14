"""SQLite store: the source of truth for documents, chunks and their embeddings.

Search never reads this at query time; it reads the in-memory Snapshot built from it.
Every write is one transaction, so a failed upsert leaves the previous state intact.
Calls come from worker threads, so one lock guards the single connection.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.kb.documents import Chunk, Document

META_VERSION = "index_version"
META_MODEL = "embedding_model"

# SQLite allows 999 bound parameters per statement in older builds.
_BATCH = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    origin TEXT NOT NULL,
    season TEXT,
    matchweek INTEGER,
    team_ids TEXT NOT NULL,
    date TEXT,
    fetched_at TEXT,
    url TEXT,
    topic TEXT,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    ord INTEGER NOT NULL,
    text TEXT NOT NULL,
    bm25_text TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chunks_doc_id ON chunks(doc_id);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_UPSERT_META = (
    "INSERT INTO meta (key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
)


@dataclass(frozen=True, slots=True)
class StoredChunk:
    chunk: Chunk
    document: Document
    embedding: np.ndarray


_DOCUMENT_COLUMNS = (
    "d.doc_id, d.title, d.category, d.origin, d.text, d.season, d.matchweek, "
    "d.team_ids, d.date, d.fetched_at, d.url, d.topic"
)


def _document(row: Sequence[Any]) -> Document:
    return Document(
        doc_id=row[0],
        title=row[1],
        category=row[2],
        origin=row[3],
        text=row[4],
        season=row[5],
        matchweek=row[6],
        team_ids=tuple(json.loads(row[7])),
        date=row[8],
        fetched_at=row[9],
        url=row[10],
        topic=row[11],
    )


def _to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32).copy()


class KnowledgeStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else None

    def get_hashes(self, doc_ids: Iterable[str]) -> dict[str, str]:
        ids = list(doc_ids)
        hashes: dict[str, str] = {}
        with self._lock:
            for start in range(0, len(ids), _BATCH):
                batch = ids[start : start + _BATCH]
                placeholders = ",".join("?" * len(batch))
                rows = self._conn.execute(
                    # Only "?" placeholders are formatted in; values stay bound.
                    f"SELECT doc_id, content_hash FROM documents WHERE doc_id IN ({placeholders})",  # noqa: S608
                    batch,
                )
                hashes.update({str(doc_id): str(value) for doc_id, value in rows})
        return hashes

    def replace_documents(
        self,
        documents: Sequence[Document],
        chunks: Mapping[str, Sequence[Chunk]],
        embeddings: Mapping[str, np.ndarray],
        *,
        updated_at: str,
        meta: Mapping[str, str],
    ) -> None:
        """Replace each document and all of its chunks, and set meta, in one transaction."""
        with self._lock, self._conn:
            for doc in documents:
                # Cascades to the document's old chunks.
                self._conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc.doc_id,))
                self._conn.execute(
                    "INSERT INTO documents (doc_id, title, category, origin, season, matchweek, "
                    "team_ids, date, fetched_at, url, topic, text, content_hash, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        doc.doc_id,
                        doc.title,
                        doc.category,
                        doc.origin,
                        doc.season,
                        doc.matchweek,
                        json.dumps(list(doc.team_ids)),
                        doc.date,
                        doc.fetched_at,
                        doc.url,
                        doc.topic,
                        doc.text,
                        doc.content_hash(),
                        updated_at,
                    ),
                )
                self._conn.executemany(
                    "INSERT INTO chunks (chunk_id, doc_id, ord, text, bm25_text, embedding) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            c.chunk_id,
                            c.doc_id,
                            c.ord,
                            c.text,
                            c.bm25_text,
                            _to_blob(embeddings[c.chunk_id]),
                        )
                        for c in chunks[doc.doc_id]
                    ],
                )
            self._conn.executemany(_UPSERT_META, list(meta.items()))

    def delete_document(self, doc_id: str, *, meta: Mapping[str, str]) -> bool:
        """Delete a document and its chunks, and set meta, in one transaction.

        Returns False, and changes nothing, when there is no such document.
        """
        with self._lock, self._conn:
            # Cascades to the document's chunks.
            cursor = self._conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            if cursor.rowcount == 0:
                return False
            self._conn.executemany(_UPSERT_META, list(meta.items()))
        return True

    def update_embeddings(
        self, embeddings: Mapping[str, np.ndarray], *, meta: Mapping[str, str]
    ) -> None:
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE chunks SET embedding = ? WHERE chunk_id = ?",
                [(_to_blob(vector), chunk_id) for chunk_id, vector in embeddings.items()],
            )
            self._conn.executemany(_UPSERT_META, list(meta.items()))

    def load_all(self) -> list[StoredChunk]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_DOCUMENT_COLUMNS}, "  # noqa: S608 - a constant column list
                "c.chunk_id, c.ord, c.text, c.bm25_text, c.embedding "
                "FROM chunks c JOIN documents d ON d.doc_id = c.doc_id "
                "ORDER BY d.doc_id, c.ord"
            ).fetchall()
        documents: dict[str, Document] = {}
        stored: list[StoredChunk] = []
        for row in rows:
            doc_id = row[0]
            if doc_id not in documents:
                documents[doc_id] = _document(row)
            chunk = Chunk(
                chunk_id=row[12], doc_id=doc_id, ord=row[13], text=row[14], bm25_text=row[15]
            )
            stored.append(StoredChunk(chunk, documents[doc_id], _from_blob(row[16])))
        return stored

    def load_documents(self, category: str | None = None) -> list[Document]:
        """Documents without their chunks, by doc_id; one category or all of them."""
        query = f"SELECT {_DOCUMENT_COLUMNS} FROM documents d"  # noqa: S608 - constant columns
        with self._lock:
            if category is None:
                rows = self._conn.execute(f"{query} ORDER BY d.doc_id").fetchall()
            else:
                rows = self._conn.execute(
                    f"{query} WHERE d.category = ? ORDER BY d.doc_id", (category,)
                ).fetchall()
        return [_document(row) for row in rows]
