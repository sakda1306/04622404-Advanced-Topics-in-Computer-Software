"""jobs, agent_runs and data_exports (docs/03_data_design.md sections 3.7, 3.8, 3.11)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import AgentRunStatus, ExportStatus, JobStage, JobStatus, JobType
from app.infrastructure.db.base import (
    Base,
    CreatedAt,
    UUIDPrimaryKey,
    check_in,
    tz_datetime,
)


class DataExportModel(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "data_exports"
    __table_args__ = (
        check_in("status", "status", ExportStatus),
        Index("ix_data_exports_user_id", "user_id"),
        Index("ix_data_exports_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'queued'"))
    object_key: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    expires_at: Mapped[datetime | None] = mapped_column(tz_datetime())


class JobModel(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        check_in("type", "type", JobType),
        check_in("status", "status", JobStatus),
        check_in("stage", "stage", JobStage),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
        CheckConstraint("num_nonnulls(recommendation_id, export_id) = 1", name="single_target"),
        Index("ix_jobs_user_recent", "user_id", text("created_at DESC")),
        # Admin listing by time (D-93).
        Index("ix_jobs_recent", text("created_at DESC"), text("id DESC")),
        Index(
            "ix_jobs_active",
            "created_at",
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_jobs_expires_at", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(24))
    recommendation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE")
    )
    export_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_exports.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16), server_default=text("'queued'"))
    stage: Mapped[str] = mapped_column(String(24), server_default=text("'queued'"))
    progress: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(40))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    started_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    finished_at: Mapped[datetime | None] = mapped_column(tz_datetime())
    expires_at: Mapped[datetime] = mapped_column(tz_datetime())


class AgentRunModel(UUIDPrimaryKey, Base):
    """Diagnostics of one Agent call; `id` is the run_id sent to the Agent. No personal data."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        check_in("status", "status", AgentRunStatus),
        UniqueConstraint("job_id", "attempt", name="uq_agent_runs_job_attempt"),
        Index("ix_agent_runs_started_at", "started_at"),
    )

    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    attempt: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(16))
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    error_code: Mapped[str | None] = mapped_column(String(40))
    duration_ms: Mapped[int | None]
    tool_calls: Mapped[int | None] = mapped_column(SmallInteger)
    agent_version: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(tz_datetime())
    finished_at: Mapped[datetime | None] = mapped_column(tz_datetime())
