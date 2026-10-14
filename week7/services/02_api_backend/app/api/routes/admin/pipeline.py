"""Data pipeline page (Must): 07 status, jobs, run ingest, generate the weekly report."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse

from app.api.deps import AdminUser, ContainerDep, DbDep, actor_tag
from app.schemas.admin import GenerateReportRequest, IngestRequest
from app.services.audit import write_audit

router = APIRouter()

JobId = Annotated[str, Path(max_length=64, pattern=r"^[A-Za-z0-9-]+$")]


@router.get("/pipeline")
async def pipeline(container: ContainerDep) -> dict[str, Any]:
    status = await container.football.status()
    jobs = await container.football.jobs(limit=20)
    return {"status": status, "jobs": jobs.get("jobs", [])}


@router.post("/pipeline/ingest", status_code=202)
async def run_ingest(
    body: IngestRequest, container: ContainerDep, db: DbDep, admin: AdminUser
) -> JSONResponse:
    result = await container.football.run_ingest(body.scope, actor_tag(admin))
    await write_audit(
        db, admin, "pipeline.ingest", body.scope, after={"job_id": result.get("job_id")}
    )
    return JSONResponse(
        {"job_id": result.get("job_id"), "scope": result.get("scope", body.scope)}, status_code=202
    )


@router.post("/reports/generate", status_code=202)
async def generate_report(
    body: GenerateReportRequest, container: ContainerDep, db: DbDep, admin: AdminUser
) -> JSONResponse:
    result = await container.football.run_weekly_report(
        body.season, body.matchweek, actor_tag(admin)
    )
    target = (
        f"weekly-{body.season}-mw{body.matchweek:02d}"
        if body.season and body.matchweek
        else "weekly-latest"
    )
    await write_audit(db, admin, "report.generate", target, after={"job_id": result.get("job_id")})
    return JSONResponse({"job_id": result.get("job_id")}, status_code=202)


@router.get("/jobs/{job_id}")
async def job(job_id: JobId, container: ContainerDep) -> Any:
    return await container.football.job(job_id)
