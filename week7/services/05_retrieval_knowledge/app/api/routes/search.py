"""POST /search (CONTRACT §4)."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.core.errors import AppError, ErrorCode
from app.core.ids import current_request_id
from app.schemas.search import ChunkOut, SearchRequest, SearchResponse, SourceOut
from app.search.hybrid import Hit
from app.search.snapshot import IndexedChunk

router = APIRouter(tags=["search"])


def _chunk_out(record: IndexedChunk, hit: Hit, ref: int) -> ChunkOut:
    doc = record.document
    return ChunkOut(
        chunk_id=record.chunk.chunk_id,
        text=record.chunk.text,
        score=hit.score,
        bm25_score=hit.bm25_score,
        vector_score=hit.vector_score,
        rerank_score=hit.rerank_score,
        source=SourceOut(
            ref=ref,
            doc_id=doc.doc_id,
            title=doc.title,
            category=doc.category,
            origin=doc.origin,
            season=doc.season,
            matchweek=doc.matchweek,
            team_ids=list(doc.team_ids),
            fetched_at=doc.fetched_at,
            url=doc.url,
            topic=doc.topic,
        ),
    )


@router.post("/search")
async def search(body: SearchRequest, container: ContainerDep) -> SearchResponse:
    started = time.perf_counter()
    snapshot = container.index.snapshot
    if snapshot is None:
        raise AppError(ErrorCode.INDEX_NOT_READY)
    hits = await asyncio.to_thread(
        container.searcher.search,
        snapshot,
        query=body.query,
        query_original=body.query_original,
        top_k=body.top_k,
        filters=body.filters.to_filters(),
        mode=body.mode,
    )
    return SearchResponse(
        request_id=body.request_id or current_request_id(),
        chunks=[
            _chunk_out(snapshot.records[hit.position], hit, ref)
            for ref, hit in enumerate(hits, start=1)
        ],
        latency_ms=int((time.perf_counter() - started) * 1000),
        index_version=snapshot.index_version,
    )
