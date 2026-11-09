"""SQLite file holding chunks and their embeddings, so a restart does not embed everything again.

It is rebuilt from /data (Design.md §5). Search never reads it: it reads the in-memory Snapshot.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path

import numpy as np

from app.rag.chunking import Chunk

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    category TEXT NOT NULL,
    role_id TEXT,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    sources TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
_META_MODEL = "embedding_model"


class RagStore:
    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript(_SCHEMA)

    def known_vectors(self, model_name: str) -> dict[str, np.ndarray]:
        """Vectors by content hash; none when they came from another model."""
        with closing(sqlite3.connect(self._path)) as db:
            row = db.execute("SELECT value FROM meta WHERE key = ?", (_META_MODEL,)).fetchone()
            if row is None or row[0] != model_name:
                return {}
            rows = db.execute("SELECT content_hash, embedding FROM chunks").fetchall()
        return {key: np.frombuffer(blob, dtype=np.float32).copy() for key, blob in rows}

    def replace_all(
        self, chunks: Sequence[Chunk], vectors: Mapping[str, np.ndarray], *, model_name: str
    ) -> None:
        """All chunks and the model name change together, or nothing does."""
        with closing(sqlite3.connect(self._path)) as db, db:
            db.execute("DELETE FROM chunks")
            db.executemany(
                "INSERT INTO chunks (chunk_id, doc_id, category, role_id, title, text, sources, "
                "content_hash, embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        c.chunk_id,
                        c.doc_id,
                        c.category,
                        c.role_id,
                        c.title,
                        c.text,
                        json.dumps(list(c.sources)),
                        c.content_hash(),
                        np.asarray(vectors[c.chunk_id], dtype=np.float32).tobytes(),
                    )
                    for c in chunks
                ],
            )
            db.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_META_MODEL, model_name),
            )
