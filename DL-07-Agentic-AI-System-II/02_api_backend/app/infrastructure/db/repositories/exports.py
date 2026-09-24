"""Data export requests and the data they contain (docs/03_data_design.md 3.11, 6.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.enums import ExportStatus
from app.domain.normalization import GeoPoint
from app.infrastructure.db.models import (
    ConversationModel,
    DataExportModel,
    FeedbackModel,
    MessageModel,
    RecommendationModel,
    UserModel,
)
from app.infrastructure.db.repositories.requests import load_request, preferences_json
from app.infrastructure.db.repositories.trips import SqlTripRepository
from app.services.ports import ExportRecord

_ALL_TRIPS = 10_000


def _record(row: DataExportModel) -> ExportRecord:
    return ExportRecord(
        id=row.id,
        user_id=row.user_id,
        status=ExportStatus(row.status),
        object_key=row.object_key,
        created_at=row.created_at,
        completed_at=row.completed_at,
        expires_at=row.expires_at,
    )


def _point(point: GeoPoint) -> dict[str, Any]:
    return {"lat": point.lat, "lon": point.lon, "name": point.name}


class SqlExportRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, user_id: UUID, *, now: datetime) -> ExportRecord:
        row = DataExportModel(
            id=new_id(), user_id=user_id, status=ExportStatus.QUEUED.value, created_at=now
        )
        async with self._sessions() as session, session.begin():
            session.add(row)
        return _record(row)

    async def get(self, user_id: UUID, export_id: UUID) -> ExportRecord | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(DataExportModel).where(
                    DataExportModel.id == export_id, DataExportModel.user_id == user_id
                )
            )
            return _record(row) if row is not None else None

    async def start(self, export_id: UUID) -> UUID | None:
        """Queued -> running; the owner, or None when the export is not waiting."""
        async with self._sessions() as session, session.begin():
            row = await session.get(DataExportModel, export_id, with_for_update=True)
            if row is None or row.status != ExportStatus.QUEUED.value:
                return None
            row.status = ExportStatus.RUNNING.value
            return row.user_id

    async def finish(
        self, export_id: UUID, *, object_key: str, now: datetime, expires_at: datetime
    ) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(DataExportModel)
                .where(DataExportModel.id == export_id)
                .values(
                    status=ExportStatus.READY.value,
                    object_key=object_key,
                    completed_at=now,
                    expires_at=expires_at,
                )
            )

    async def fail(self, export_id: UUID, *, now: datetime) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(DataExportModel)
                .where(DataExportModel.id == export_id)
                .values(status=ExportStatus.FAILED.value, completed_at=now)
            )

    async def fail_stuck(self, *, older_than: datetime, now: datetime) -> int:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(DataExportModel)
                .where(
                    DataExportModel.status.in_(
                        (ExportStatus.QUEUED.value, ExportStatus.RUNNING.value)
                    ),
                    DataExportModel.created_at < older_than,
                )
                .values(status=ExportStatus.FAILED.value, completed_at=now)
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def object_keys(self, user_id: UUID) -> list[str]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(DataExportModel.object_key).where(
                    DataExportModel.user_id == user_id, DataExportModel.object_key.is_not(None)
                )
            )
            return [key for key in rows if key]

    async def collect(self, user_id: UUID) -> dict[str, Any]:
        """Everything stored about the user, readable (docs/03_data_design.md 6.3)."""
        trips = await SqlTripRepository(self._sessions).list_trips(
            user_id, limit=_ALL_TRIPS, cursor=None, status=None
        )
        async with self._sessions() as session:
            user = await session.get(UserModel, user_id)
            if user is None:
                return {}
            conversations = []
            for chat in await session.scalars(
                select(ConversationModel)
                .where(ConversationModel.user_id == user_id)
                .order_by(ConversationModel.created_at)
            ):
                messages = await session.scalars(
                    select(MessageModel)
                    .where(MessageModel.conversation_id == chat.id)
                    .order_by(MessageModel.created_at, MessageModel.id)
                )
                conversations.append(
                    {
                        "conversation_id": chat.id,
                        "title": chat.title,
                        "language": chat.language,
                        "created_at": chat.created_at,
                        "messages": [
                            {
                                "role": m.role,
                                "content": m.content,
                                "recommendation_id": m.recommendation_id,
                                "created_at": m.created_at,
                            }
                            for m in messages
                        ],
                    }
                )
            recommendations = []
            for rec in await session.scalars(
                select(RecommendationModel)
                .where(RecommendationModel.user_id == user_id)
                .order_by(RecommendationModel.created_at)
            ):
                request, _ = await load_request(session, rec.request_id, question=None)
                recommendations.append(
                    {
                        "recommendation_id": rec.id,
                        "created_at": rec.created_at,
                        "status": rec.status,
                        "request": {
                            "origin": _point(request.origin),
                            "destination": _point(request.destination),
                            "waypoints": [_point(p) for p in request.waypoints],
                            "departure_time": request.departure_time,
                            "timezone": request.timezone,
                            "language": request.language,
                            "preferences": preferences_json(request.preferences),
                        },
                        "result": rec.payload,
                    }
                )
            feedback = [
                {
                    "feedback_id": row.id,
                    "recommendation_id": row.recommendation_id,
                    "rating": row.rating,
                    "helpful": row.helpful,
                    "outcome": row.outcome,
                    "report_type": row.report_type,
                    "comment": row.comment,
                    "review_status": row.review_status,
                    "created_at": row.created_at,
                }
                for row in await session.scalars(
                    select(FeedbackModel)
                    .where(FeedbackModel.pseudonymous_id == user.pseudonymous_id)
                    .order_by(FeedbackModel.created_at)
                )
            ]
            profile = {
                "user_id": user.id,
                "display_name": user.display_name,
                "language": user.language,
                "timezone": user.timezone,
                "home_region": user.home_region,
                "consents": {
                    "live_alerts": user.consent_live_alerts,
                    "live_alerts_at": user.consent_live_alerts_at,
                    "analytics": user.consent_analytics,
                    "analytics_at": user.consent_analytics_at,
                },
                "created_at": user.created_at,
            }
        return {
            "profile": profile,
            "conversations": conversations,
            "trips": [
                {
                    "trip_id": trip.id,
                    "name": trip.draft.name,
                    "origin": _point(trip.draft.origin),
                    "destination": _point(trip.draft.destination),
                    "waypoints": [_point(p) for p in trip.draft.waypoints],
                    "departure_time": trip.draft.departure_time,
                    "timezone": trip.draft.timezone,
                    "preferences": preferences_json(trip.draft.preferences),
                    "status": trip.draft.status.value,
                    "alerts_enabled": trip.draft.alerts.enabled,
                    "created_at": trip.created_at,
                }
                for trip in trips
            ],
            "recommendations": recommendations,
            "feedback": feedback,
        }
