"""Shared resources on `app.state` and how they are built."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.index.jobs import RebuildJobs
from app.index.service import IndexService
from app.kb.store import KnowledgeStore
from app.search.aliases import AliasProvider, load_alias_file
from app.search.embedder import Embedder, SentenceTransformerEmbedder
from app.search.hybrid import Searcher
from app.search.reranker import load_reranker


@dataclass
class Container:
    settings: Settings
    store: KnowledgeStore
    index: IndexService
    searcher: Searcher
    aliases: AliasProvider
    jobs: RebuildJobs


def build_container(settings: Settings, *, embedder: Embedder | None = None) -> Container:
    embedder = embedder or SentenceTransformerEmbedder(settings.embedding_model)
    store = KnowledgeStore(settings.kb_db_path)
    aliases = AliasProvider(load_alias_file(settings.aliases_file))
    searcher = Searcher(
        embedder,
        aliases,
        reranker=load_reranker(settings.rerank_model),
        candidate_k=settings.candidate_k,
        rrf_k=settings.rrf_k,
        min_vector_score=settings.min_vector_score,
    )
    index = IndexService(store, embedder)
    return Container(settings, store, index, searcher, aliases, RebuildJobs(index))


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]
