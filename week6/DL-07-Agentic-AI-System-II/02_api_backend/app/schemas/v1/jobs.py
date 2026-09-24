"""API contract for jobs and progress streams (docs/02_api_spec.md section 6)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.errors import ERROR_SPECS, ErrorCode
from app.domain.enums import JobStage, JobStatus, JobType
from app.services.ports import JobRecord


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobError(_Strict):
    code: str
    message: str


class JobResponse(_Strict):
    job_id: UUID
    type: JobType
    status: JobStatus
    stage: JobStage
    progress: int
    created_at: datetime
    updated_at: datetime
    result_url: str | None
    error: JobError | None

    @classmethod
    def from_record(cls, job: JobRecord) -> JobResponse:
        error = None
        if job.error_code is not None:
            known = {code.value for code in ErrorCode}
            message = (
                ERROR_SPECS[ErrorCode(job.error_code)].detail
                if job.error_code in known
                else "The request could not be completed."
            )
            error = JobError(code=job.error_code, message=message)
        return cls(
            job_id=job.id,
            type=job.type,
            status=job.status,
            stage=job.stage,
            progress=job.progress,
            created_at=job.created_at,
            updated_at=job.updated_at,
            result_url=(
                f"/v1/travel/recommendations/{job.recommendation_id}"
                if job.recommendation_id
                else None
            ),
            error=error,
        )


class StreamTicketResponse(_Strict):
    ticket: str
    expires_in: int
