"""The search index the app uses: rebuilt from /data, held in memory (Design.md §5, §6).

`build` and `search` run the embedding model on the CPU, so async code calls them with
`asyncio.to_thread`.
"""

from __future__ import annotations

from app.rag.chunking import load_chunks
from app.rag.embedder import Embedder
from app.rag.hybrid import Hit, Mode, search
from app.rag.snapshot import IndexedChunk, SearchFilters, Snapshot
from app.rag.store import RagStore
from app.rag.tokenize import tokenize


class RagIndex:
    def __init__(self, *, data_dir: str, db_path: str, embedder: Embedder) -> None:
        self._data_dir = data_dir
        self._store = RagStore(db_path)
        self._embedder = embedder
        self._snapshot: Snapshot | None = None

    def build(self) -> None:
        """Embeds only new or changed chunks. On failure the old index and store stay."""
        chunks = load_chunks(self._data_dir)
        model_name = self._embedder.model_name
        known = self._store.known_vectors(model_name)
        new = [c for c in chunks if c.content_hash() not in known]
        fresh = self._embedder.encode_passages([c.text for c in new])
        new_vectors = {c.chunk_id: vector for c, vector in zip(new, fresh, strict=True)}
        vectors = {
            c.chunk_id: new_vectors.get(c.chunk_id, known.get(c.content_hash())) for c in chunks
        }
        self._store.replace_all(chunks, vectors, model_name=model_name)
        records = [IndexedChunk(c, vectors[c.chunk_id], tuple(tokenize(c.text))) for c in chunks]
        self._snapshot = Snapshot(records, dimension=self._embedder.dimension)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        category: str | None = None,
        role_id: str | None = None,
        mode: Mode = "hybrid",
    ) -> list[Hit]:
        snapshot = self._snapshot
        if snapshot is None:
            raise RuntimeError("RagIndex.build must run before search")
        return search(
            snapshot,
            self._embedder,
            query=query,
            top_k=top_k,
            filters=SearchFilters(category=category, role_id=role_id),
            mode=mode,
        )
