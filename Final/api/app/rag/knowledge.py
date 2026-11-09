"""The search index as the app sees it (Design.md §4.6, §6).

The model can take minutes to download and load, so it loads in the background and the app starts
at once. Retrieval only adds to an answer: until the index is ready, or if it fails, a search finds
nothing and the routes answer from their other data.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from app.core.config import Settings
from app.rag.hybrid import Hit

if TYPE_CHECKING:
    from app.rag.index import RagIndex

log = structlog.get_logger(__name__)


class Knowledge:
    def __init__(self, index: RagIndex | None = None) -> None:
        self._index = index

    @property
    def ready(self) -> bool:
        return self._index is not None

    def load(self, settings: Settings) -> None:
        """Blocks while the model loads, so it runs in its own thread."""
        if not settings.embed_model:
            log.info("rag_disabled", reason="EMBED_MODEL is not set")
            return
        # Imported here: torch and faiss are heavy, and tests never load them through this path.
        from app.rag.embedder import SentenceTransformerEmbedder
        from app.rag.index import RagIndex

        try:
            index = RagIndex(
                data_dir=settings.data_dir,
                db_path=settings.rag_db_path,
                embedder=SentenceTransformerEmbedder(settings.embed_model),
            )
            index.build()
        except Exception:
            log.exception("rag_load_failed", model=settings.embed_model)
            return
        self._index = index
        log.info("rag_ready", model=settings.embed_model)

    async def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        category: str | None = None,
        role_id: str | None = None,
    ) -> list[Hit]:
        index = self._index
        if index is None:
            return []
        try:
            # The embedding model runs on the CPU, so it stays off the event loop.
            return await asyncio.to_thread(
                index.search, query, top_k=top_k, category=category, role_id=role_id
            )
        except Exception:
            log.exception("rag_search_failed", category=category, role_id=role_id)
            return []
