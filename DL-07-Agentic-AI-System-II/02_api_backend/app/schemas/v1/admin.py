"""Admin contracts (docs/02_api_spec.md section 8.2). Diagnostics only (D-94)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    AuditResult,
    ExportStatus,
    JobStage,
    JobStatus,
    JobType,
    RecommendationStatus,
    RecommendationType,
    RequestSource,
    RiskLevel,
)
from app.services.ports import (
    AdminJobRecord,
    AdminRecommendationRecord,
    AgentRunView,
    AuditLogRecord,
)
from app.services.training_export_service import TrainingExportView


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AdminJob(_Strict):
    job_id: UUID
    type: JobType
    status: JobStatus
    stage: JobStage
    attempts: int
    error_code: str | None
    recommendation_id: UUID | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_record(cls, record: AdminJobRecord) -> AdminJob:
        return cls(
            job_id=record.id,
            type=record.type,
            status=record.status,
            stage=record.stage,
            attempts=record.attempts,
            error_code=record.error_code,
            recommendation_id=record.recommendation_id,
            cancel_requested=record.cancel_requested,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )


class AdminJobPage(_Strict):
    items: list[AdminJob]
    next_cursor: str | None


class AgentRun(_Strict):
    run_id: UUID
    attempt: int
    status: AgentRunStatus
    http_status: int | None
    error_code: str | None
    duration_ms: int | None
    tool_calls: int | None
    agent_version: str | None
    trace_id: str | None
    started_at: datetime
    finished_at: datetime | None

    @classmethod
    def from_view(cls, view: AgentRunView) -> AgentRun:
        return cls(
            run_id=view.run_id,
            attempt=view.attempt,
            status=view.status,
            http_status=view.http_status,
            error_code=view.error_code,
            duration_ms=view.duration_ms,
            tool_calls=view.tool_calls,
            agent_version=view.agent_version,
            trace_id=view.trace_id,
            started_at=view.started_at,
            finished_at=view.finished_at,
        )


class AdminRecommendation(_Strict):
    recommendation_id: UUID
    source: RequestSource
    status: RecommendationStatus
    risk_level: RiskLevel | None
    risk_score: float | None
    risk_confidence: float | None
    recommendation_type: RecommendationType | None
    warning_codes: list[str]
    safety_gate_rules: list[str]
    overall_is_stale: bool | None
    error_code: str | None
    versions: dict[str, str | None]
    data_freshness: list[dict[str, Any]]
    service_status: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None
    valid_until: datetime | None
    job: AdminJob | None
    agent_runs: list[AgentRun]

    @classmethod
    def from_record(cls, record: AdminRecommendationRecord) -> AdminRecommendation:
        return cls(
            recommendation_id=record.id,
            source=record.source,
            status=record.status,
            risk_level=record.risk_level,
            risk_score=record.risk_score,
            risk_confidence=record.risk_confidence,
            recommendation_type=record.recommendation_type,
            warning_codes=list(record.warning_codes),
            safety_gate_rules=list(record.safety_gate_rules),
            overall_is_stale=record.overall_is_stale,
            error_code=record.error_code,
            versions=record.versions,
            data_freshness=record.data_freshness,
            service_status=record.service_status,
            created_at=record.created_at,
            completed_at=record.completed_at,
            valid_until=record.valid_until,
            job=AdminJob.from_record(record.job) if record.job else None,
            agent_runs=[AgentRun.from_view(run) for run in record.agent_runs],
        )


class AuditLogItem(_Strict):
    id: int
    occurred_at: datetime
    actor_type: ActorType
    actor_ref: str
    action: str
    target_type: str | None
    target_id: str | None
    result: AuditResult
    correlation_id: str
    metadata: dict[str, Any]

    @classmethod
    def from_record(cls, record: AuditLogRecord) -> AuditLogItem:
        return cls(
            id=record.id,
            occurred_at=record.occurred_at,
            actor_type=record.actor_type,
            actor_ref=record.actor_ref,
            action=record.action,
            target_type=record.target_type,
            target_id=record.target_id,
            result=record.result,
            correlation_id=record.correlation_id,
            metadata=record.metadata,
        )


class AuditLogPage(_Strict):
    items: list[AuditLogItem]
    next_cursor: str | None


class TrainingExportRequest(_Strict):
    range_from: datetime | None = Field(default=None, alias="from")
    range_to: datetime | None = Field(default=None, alias="to")


class TrainingExportAccepted(_Strict):
    export_id: UUID
    status: ExportStatus


class TrainingExportResponse(_Strict):
    export_id: UUID
    status: ExportStatus
    range_from: datetime = Field(alias="from")
    range_to: datetime = Field(alias="to")
    row_count: int | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    # Short-lived signed link (P-62); only while the file exists.
    download_url: str | None

    @classmethod
    def from_view(cls, view: TrainingExportView) -> TrainingExportResponse:
        record = view.record
        return cls(
            export_id=record.id,
            status=record.status,
            range_from=record.range_from,
            range_to=record.range_to,
            row_count=record.row_count,
            created_at=record.created_at,
            completed_at=record.completed_at,
            expires_at=record.expires_at,
            download_url=view.download_url,
        )
