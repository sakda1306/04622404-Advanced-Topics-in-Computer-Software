"""Read-only queries for admin tools (docs/02_api_spec.md section 8.2).

Every query is bounded by a time range and ordered newest first with a keyset cursor.
Only diagnostic columns are selected: never user ids, places, coordinates, questions
or answers (D-94).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.admin import AuditFilter, TimeRange
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    AuditResult,
    JobStage,
    JobStatus,
    JobType,
    RecommendationStatus,
    RecommendationType,
    RequestSource,
    RiskLevel,
)
from app.infrastructure.db.models import (
    AgentRunModel,
    AuditLogModel,
    JobModel,
    RecommendationModel,
    TravelRequestModel,
)
from app.services.pagination import Cursor
from app.services.ports import (
    AdminJobRecord,
    AdminRecommendationRecord,
    AgentRunView,
    AuditLogRecord,
)

_JOB_COLUMNS = (
    JobModel.id,
    JobModel.type,
    JobModel.status,
    JobModel.stage,
    JobModel.attempts,
    JobModel.error_code,
    JobModel.recommendation_id,
    JobModel.cancel_requested_at,
    JobModel.created_at,
    JobModel.started_at,
    JobModel.finished_at,
)


def _job(row: Any) -> AdminJobRecord:
    return AdminJobRecord(
        id=row.id,
        type=JobType(row.type),
        status=JobStatus(row.status),
        stage=JobStage(row.stage),
        attempts=row.attempts,
        error_code=row.error_code,
        recommendation_id=row.recommendation_id,
        cancel_requested=row.cancel_requested_at is not None,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _run(row: AgentRunModel) -> AgentRunView:
    return AgentRunView(
        run_id=row.id,
        attempt=row.attempt,
        status=AgentRunStatus(row.status),
        http_status=row.http_status,
        error_code=row.error_code,
        duration_ms=row.duration_ms,
        tool_calls=row.tool_calls,
        agent_version=row.agent_version,
        trace_id=row.trace_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _freshness(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Category, time and staleness only; nothing else from the answer."""
    items = ((payload or {}).get("data_freshness") or {}).get("items") or []
    keep = ("category", "updated_at", "age_seconds", "is_stale")
    return [{k: item.get(k) for k in keep} for item in items if isinstance(item, dict)]


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _keyset(query: Select[Any], columns: tuple[Any, Any], cursor: Cursor | None) -> Select[Any]:
    if cursor is None:
        return query
    return query.where(tuple_(*columns) < (cursor.at, cursor.id))


class SqlAdminRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def jobs(
        self,
        *,
        period: TimeRange,
        status: JobStatus | None,
        job_type: JobType | None,
        limit: int,
        cursor: Cursor | None,
    ) -> list[AdminJobRecord]:
        query = select(*_JOB_COLUMNS).where(
            JobModel.created_at >= period.start, JobModel.created_at < period.end
        )
        if status is not None:
            query = query.where(JobModel.status == status.value)
        if job_type is not None:
            query = query.where(JobModel.type == job_type.value)
        query = _keyset(query, (JobModel.created_at, JobModel.id), cursor)
        query = query.order_by(JobModel.created_at.desc(), JobModel.id.desc()).limit(limit + 1)
        async with self._sessions() as session:
            return [_job(row) for row in await session.execute(query)]

    async def recommendation(self, recommendation_id: UUID) -> AdminRecommendationRecord | None:
        async with self._sessions() as session:
            found = (
                await session.execute(
                    select(RecommendationModel, TravelRequestModel.source)
                    .join(
                        TravelRequestModel,
                        TravelRequestModel.id == RecommendationModel.request_id,
                    )
                    .where(RecommendationModel.id == recommendation_id)
                )
            ).first()
            if found is None:
                return None
            rec, source = found
            job = (
                await session.execute(
                    select(*_JOB_COLUMNS)
                    .where(JobModel.recommendation_id == recommendation_id)
                    .order_by(JobModel.created_at.desc())
                    .limit(1)
                )
            ).first()
            runs: list[AgentRunModel] = []
            if job is not None:
                runs = list(
                    await session.scalars(
                        select(AgentRunModel)
                        .where(AgentRunModel.job_id == job.id)
                        .order_by(AgentRunModel.attempt)
                    )
                )
        return AdminRecommendationRecord(
            id=rec.id,
            source=RequestSource(source),
            status=RecommendationStatus(rec.status),
            risk_level=RiskLevel(rec.risk_level) if rec.risk_level else None,
            risk_score=_float(rec.risk_score),
            risk_confidence=_float(rec.risk_confidence),
            recommendation_type=(
                RecommendationType(rec.recommendation_type) if rec.recommendation_type else None
            ),
            warning_codes=tuple(rec.warning_codes),
            safety_gate_rules=tuple(rec.safety_gate_rules),
            overall_is_stale=rec.overall_is_stale,
            error_code=rec.error_code,
            versions={
                "api": rec.api_version,
                "agent": rec.agent_version,
                "risk_model": rec.risk_model_version,
                "prompt": rec.prompt_version,
            },
            data_freshness=_freshness(rec.payload),
            service_status=dict((rec.payload or {}).get("service_status") or {}),
            created_at=rec.created_at,
            completed_at=rec.completed_at,
            valid_until=rec.valid_until,
            job=_job(job) if job is not None else None,
            agent_runs=tuple(_run(run) for run in runs),
        )

    async def audit_logs(
        self, *, period: TimeRange, where: AuditFilter, limit: int, cursor: Cursor | None
    ) -> list[AuditLogRecord]:
        model = AuditLogModel
        query = select(
            model.id,
            model.occurred_at,
            model.actor_type,
            model.actor_ref,
            model.action,
            model.target_type,
            model.target_id,
            model.result,
            model.correlation_id,
            model.metadata_,
        ).where(model.occurred_at >= period.start, model.occurred_at < period.end)
        for column, value in (
            (model.action, where.action),
            (model.actor_type, where.actor_type),
            (model.result, where.result),
            (model.target_type, where.target_type),
            (model.target_id, where.target_id),
        ):
            if value is not None:
                query = query.where(column == value)
        query = _keyset(query, (model.occurred_at, model.id), cursor)
        query = query.order_by(model.occurred_at.desc(), model.id.desc()).limit(limit + 1)
        async with self._sessions() as session:
            rows = await session.execute(query)
            return [
                AuditLogRecord(
                    id=row.id,
                    occurred_at=row.occurred_at,
                    actor_type=ActorType(row.actor_type),
                    actor_ref=row.actor_ref,
                    action=row.action,
                    target_type=row.target_type,
                    target_id=row.target_id,
                    result=AuditResult(row.result),
                    correlation_id=row.correlation_id,
                    metadata=dict(row.metadata_ or {}),
                )
                for row in rows
            ]
