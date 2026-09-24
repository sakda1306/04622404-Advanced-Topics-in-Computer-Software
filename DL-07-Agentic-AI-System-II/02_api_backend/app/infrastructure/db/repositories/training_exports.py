"""Training data exports (docs/03_data_design.md 3.14, D-92).

A row is a prediction record (already anonymized, written only with analytics consent)
plus the feedback on it that a safety reviewer approved for training. Recommendation
ids, pseudonymous ids and feedback comments are left out.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.admin import TimeRange
from app.domain.enums import ExportStatus
from app.infrastructure.db.models import FeedbackModel, PredictionRecordModel, TrainingExportModel
from app.services.ports import TrainingExportRecord


def _record(row: TrainingExportModel) -> TrainingExportRecord:
    return TrainingExportRecord(
        id=row.id,
        requested_by=row.requested_by,
        status=ExportStatus(row.status),
        range_from=row.range_from,
        range_to=row.range_to,
        row_count=row.row_count,
        object_key=row.object_key,
        created_at=row.created_at,
        completed_at=row.completed_at,
        expires_at=row.expires_at,
    )


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _number(value: Any) -> float | None:
    return float(value) if value is not None else None


def _line(row: PredictionRecordModel, feedback: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "prediction_id": str(row.id),
        "created_at": _iso(row.created_at),
        "origin_geohash": row.origin_geohash,
        "destination_geohash": row.destination_geohash,
        "region_code": row.region_code,
        "departure_bucket": _iso(row.departure_bucket),
        "lead_time_hours": row.lead_time_hours,
        "travel_modes": list(row.travel_modes),
        "status": row.status,
        "risk_level": row.risk_level,
        "risk_score": _number(row.risk_score),
        "risk_confidence": _number(row.risk_confidence),
        "recommendation_type": row.recommendation_type,
        "hazard_types": list(row.hazard_types),
        "data_freshness": row.data_freshness,
        "service_status": row.service_status,
        "safety_gate_rules": list(row.safety_gate_rules),
        "versions": {
            "agent": row.agent_version,
            "risk_model": row.risk_model_version,
            "prompt": row.prompt_version,
        },
        "feedback": feedback,
    }


class SqlTrainingExportRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(
        self, requested_by: str, *, period: TimeRange, now: datetime
    ) -> TrainingExportRecord:
        row = TrainingExportModel(
            id=new_id(),
            requested_by=requested_by,
            status=ExportStatus.QUEUED.value,
            range_from=period.start,
            range_to=period.end,
            created_at=now,
        )
        async with self._sessions() as session, session.begin():
            session.add(row)
        return _record(row)

    async def get(self, export_id: UUID) -> TrainingExportRecord | None:
        async with self._sessions() as session:
            row = await session.get(TrainingExportModel, export_id)
            return _record(row) if row is not None else None

    async def start(self, export_id: UUID) -> TimeRange | None:
        """Queued -> running; the range to export, or None when it is not waiting."""
        async with self._sessions() as session, session.begin():
            row = await session.get(TrainingExportModel, export_id, with_for_update=True)
            if row is None or row.status != ExportStatus.QUEUED.value:
                return None
            row.status = ExportStatus.RUNNING.value
            return TimeRange(row.range_from, row.range_to)

    async def rows(self, period: TimeRange, *, batch: int) -> AsyncIterator[dict[str, Any]]:
        model = PredictionRecordModel
        after: tuple[datetime, UUID] | None = None
        while True:
            query = select(model).where(
                model.created_at >= period.start, model.created_at < period.end
            )
            if after is not None:
                query = query.where(tuple_(model.created_at, model.id) > after)
            query = query.order_by(model.created_at, model.id).limit(batch)
            async with self._sessions() as session:
                records = list(await session.scalars(query))
                feedback = await self._approved_feedback(
                    session, [r.recommendation_id for r in records]
                )
            for record in records:
                yield _line(record, feedback.get(record.recommendation_id, []))
            if len(records) < batch:
                return
            after = (records[-1].created_at, records[-1].id)

    @staticmethod
    async def _approved_feedback(
        session: AsyncSession, recommendation_ids: list[UUID]
    ) -> dict[UUID, list[dict[str, Any]]]:
        if not recommendation_ids:
            return {}
        rows = await session.execute(
            select(
                FeedbackModel.recommendation_id,
                FeedbackModel.rating,
                FeedbackModel.helpful,
                FeedbackModel.outcome,
                FeedbackModel.report_type,
            )
            .where(
                FeedbackModel.recommendation_id.in_(recommendation_ids),
                FeedbackModel.usable_for_training.is_(True),
            )
            .order_by(FeedbackModel.created_at)
        )
        found: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            found[row.recommendation_id].append(
                {
                    "rating": row.rating,
                    "helpful": row.helpful,
                    "outcome": row.outcome,
                    "report_type": row.report_type,
                }
            )
        return found

    async def finish(
        self,
        export_id: UUID,
        *,
        object_key: str,
        row_count: int,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(TrainingExportModel)
                .where(TrainingExportModel.id == export_id)
                .values(
                    status=ExportStatus.READY.value,
                    object_key=object_key,
                    row_count=row_count,
                    completed_at=now,
                    expires_at=expires_at,
                )
            )

    async def fail(self, export_id: UUID, *, now: datetime) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(TrainingExportModel)
                .where(TrainingExportModel.id == export_id)
                .values(status=ExportStatus.FAILED.value, completed_at=now)
            )

    async def fail_stuck(self, *, older_than: datetime, now: datetime) -> int:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(TrainingExportModel)
                .where(
                    TrainingExportModel.status.in_(
                        (ExportStatus.QUEUED.value, ExportStatus.RUNNING.value)
                    ),
                    TrainingExportModel.created_at < older_than,
                )
                .values(status=ExportStatus.FAILED.value, completed_at=now)
            )
            return int(getattr(result, "rowcount", 0) or 0)
