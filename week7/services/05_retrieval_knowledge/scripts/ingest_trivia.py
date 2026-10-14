"""Load the trivia file into the Knowledge Base (week5 #2, #3). Safe to run again.

    python -m scripts.ingest_trivia

Entries that did not change are skipped, so a container restart embeds nothing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.index.service import IndexService
from app.kb.store import KnowledgeStore
from app.kb.trivia import load_nickname_documents, load_trivia_documents
from app.search.embedder import Embedder, SentenceTransformerEmbedder

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestResult:
    parsed: int
    kept: int
    duplicates: list[int]
    conflicts: list[list[int]]
    index_version: str | None
    nicknames: int = 0


async def ingest(settings: Settings, embedder: Embedder) -> IngestResult:
    documents, report = load_trivia_documents(settings.trivia_file)
    nicknames = load_nickname_documents(settings.nickname_file)[0] if settings.nickname_file else []
    store = KnowledgeStore(settings.kb_db_path)
    try:
        index = IndexService(store, embedder)
        await index.load()
        upserted = await index.upsert(documents + nicknames)
    finally:
        store.close()
    result = IngestResult(
        parsed=report.parsed,
        kept=len(documents),
        duplicates=report.duplicates,
        conflicts=report.conflicts,
        index_version=upserted.index_version,
        nicknames=len(nicknames),
    )
    log.info(
        "trivia_ingested",
        parsed=result.parsed,
        kept=result.kept,
        nicknames=result.nicknames,
        duplicates=len(result.duplicates),
        conflicts=result.conflicts,
        index_version=result.index_version,
    )
    return result


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, settings.service_name)
    asyncio.run(ingest(settings, SentenceTransformerEmbedder(settings.embedding_model)))


if __name__ == "__main__":
    main()
