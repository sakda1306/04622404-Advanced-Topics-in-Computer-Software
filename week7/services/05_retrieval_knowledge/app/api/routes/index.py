"""Index management for 07 and the admin pages (CONTRACT §6)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, status

from app.api.deps import Container, ContainerDep
from app.core.errors import AppError, ErrorCode
from app.core.ids import current_request_id
from app.index.service import index_stats
from app.schemas.index import (
    DeleteResponse,
    JobResponse,
    RebuildAccepted,
    RebuildRequest,
    StatsResponse,
    UpsertRequest,
    UpsertResponse,
)

router = APIRouter(prefix="/index", tags=["index"])


def _ready(container: Container) -> None:
    # Writes wait for the startup load like searches do; 07 retries a failed write (§6).
    if container.index.snapshot is None:
        raise AppError(ErrorCode.INDEX_NOT_READY)


@router.post("/upsert")
async def upsert(body: UpsertRequest, container: ContainerDep) -> UpsertResponse:
    _ready(container)
    result = await container.index.upsert([d.to_document() for d in body.documents])
    return UpsertResponse(
        request_id=body.request_id or current_request_id(),
        upserted=result.upserted,
        chunks=result.chunks,
        index_version=result.index_version,
    )


@router.get("/stats")
async def stats(container: ContainerDep) -> StatsResponse:
    snapshot = container.index.snapshot
    if snapshot is None:
        raise AppError(ErrorCode.INDEX_NOT_READY)
    counts = index_stats(snapshot)
    return StatsResponse(
        documents=counts.documents,
        chunks=counts.chunks,
        by_category=counts.by_category,
        index_version=counts.index_version,
    )


@router.delete("/{doc_id}")
async def delete(
    doc_id: Annotated[str, Path(max_length=128)], container: ContainerDep
) -> DeleteResponse:
    _ready(container)
    return DeleteResponse(deleted=await container.index.delete(doc_id))


@router.post("/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild(body: RebuildRequest, container: ContainerDep) -> RebuildAccepted:
    if container.index.snapshot is None:
        raise AppError(ErrorCode.INDEX_NOT_READY)
    return RebuildAccepted(job_id=container.jobs.start(body.category).job_id)


@router.get("/jobs/{job_id}")
async def job(job_id: Annotated[str, Path(max_length=64)], container: ContainerDep) -> JobResponse:
    found = container.jobs.get(job_id)
    if found is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return JobResponse(
        job_id=found.job_id,
        status=found.status,
        started_at=found.started_at,
        finished_at=found.finished_at,
        detail=found.detail,
    )
