"""GET /v1/admin/jobs (docs/02_api_spec.md section 8.2): jobs by time, newest first."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_admin_service
from app.api.v1.admin.access import admin_actor
from app.core.security import Scope
from app.domain.enums import JobStatus, JobType
from app.schemas.v1.admin import AdminJob, AdminJobPage
from app.services.admin_service import Actor, AdminService

router = APIRouter(prefix="/admin/jobs", tags=["admin"])


@router.get(
    "",
    summary="Jobs in a time range (default: the last 24 hours)",
    response_model=AdminJobPage,
)
async def list_jobs(
    status: JobStatus | None = Query(default=None),
    job_type: JobType | None = Query(default=None, alias="type"),
    start: datetime | None = Query(default=None, alias="from"),
    end: datetime | None = Query(default=None, alias="to"),
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=200),
    actor: Actor = Depends(admin_actor(Scope.ADMIN_READ, "admin.jobs_list")),
    service: AdminService = Depends(get_admin_service),
) -> AdminJobPage:
    page = await service.jobs(
        actor,
        start=start,
        end=end,
        status=status,
        job_type=job_type,
        limit=limit,
        cursor=cursor,
    )
    return AdminJobPage(
        items=[AdminJob.from_record(item) for item in page.items], next_cursor=page.next_cursor
    )
