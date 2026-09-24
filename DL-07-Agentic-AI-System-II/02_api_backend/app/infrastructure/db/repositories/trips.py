"""Saved trips (docs/03_data_design.md section 3.4).

Every user-facing query is scoped to the owner. Deleting a trip unlinks its requests and
recommendations (SET NULL), so the assessment history stays readable.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import Select, cast, delete, exists, func, or_, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.core.ids import new_id
from app.domain.enums import (
    AlertChannel,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
    TripStatus,
)
from app.domain.normalization import GeoPoint
from app.domain.retention import expires_at
from app.domain.trips import AlertSettings, TripDraft
from app.infrastructure.db.models import RecommendationModel, TripModel, UserModel
from app.infrastructure.db.repositories.recommendations import summary_record, user_ref
from app.infrastructure.db.repositories.requests import (
    parse_preferences,
    point_json,
    point_value,
    preferences_json,
)
from app.services.pagination import Cursor
from app.services.ports import (
    AssessmentSummary,
    DueTrip,
    RecommendationSummaryRecord,
    TripRecord,
    UserRef,
)

_OPEN = (TripStatus.PLANNED.value, TripStatus.ACTIVE.value)
_LAST = aliased(RecommendationModel)


def _columns(row: TripModel, draft: TripDraft) -> None:
    row.name = draft.name
    row.origin = point_value(draft.origin)
    row.origin_name = draft.origin.name
    row.destination = point_value(draft.destination)
    row.destination_name = draft.destination.name
    row.waypoints = [point_json(p) for p in draft.waypoints]
    row.departure_time = draft.departure_time
    row.timezone = draft.timezone
    row.preferences = preferences_json(draft.preferences)
    row.status = draft.status.value
    row.alerts_enabled = draft.alerts.enabled
    row.alerts_consent_at = draft.alerts.consent_at
    row.alert_channels = [c.value for c in draft.alerts.channels]


def _select() -> Select[Any]:
    origin = cast(TripModel.origin, Geometry)
    destination = cast(TripModel.destination, Geometry)
    return select(
        TripModel,
        func.ST_Y(origin),
        func.ST_X(origin),
        func.ST_Y(destination),
        func.ST_X(destination),
        _LAST,
    ).outerjoin(_LAST, _LAST.id == TripModel.last_recommendation_id)


def _record(result: Any) -> TripRecord:
    trip: TripModel = result[0]
    last: RecommendationModel | None = result[5]
    draft = TripDraft(
        name=trip.name,
        origin=GeoPoint(result[1], result[2], name=trip.origin_name),
        destination=GeoPoint(result[3], result[4], name=trip.destination_name),
        departure_time=trip.departure_time,
        timezone=trip.timezone,
        waypoints=tuple(
            GeoPoint(p["lat"], p["lon"], name=p.get("name"), place_id=p.get("place_id"))
            for p in trip.waypoints
        ),
        preferences=parse_preferences(trip.preferences),
        alerts=AlertSettings(
            enabled=trip.alerts_enabled,
            consent_at=trip.alerts_consent_at,
            channels=tuple(AlertChannel(c) for c in trip.alert_channels),
        ),
        status=TripStatus(trip.status),
    )
    summary = None
    if last is not None:
        summary = AssessmentSummary(
            recommendation_id=last.id,
            status=RecommendationStatus(last.status),
            risk_level=RiskLevel(last.risk_level) if last.risk_level else None,
            recommendation_type=(
                RecommendationType(last.recommendation_type) if last.recommendation_type else None
            ),
            created_at=last.created_at,
        )
    return TripRecord(
        id=trip.id,
        user_id=trip.user_id,
        draft=draft,
        last_assessment=summary,
        assessment_outdated=trip.assessment_outdated,
        created_at=trip.created_at,
        updated_at=trip.updated_at,
    )


async def _record_consent(
    session: AsyncSession, user_id: UUID, draft: TripDraft, now: datetime
) -> None:
    """Alerts on a trip mean the user agreed to live alerts (D-77)."""
    if not draft.alerts.enabled:
        return
    await session.execute(
        update(UserModel)
        .where(UserModel.id == user_id, UserModel.consent_live_alerts.is_(False))
        .values(consent_live_alerts=True, consent_live_alerts_at=now, updated_at=now)
    )


class SqlTripRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def _load(self, session: AsyncSession, user_id: UUID, trip_id: UUID) -> TripRecord | None:
        result = (
            await session.execute(
                _select().where(TripModel.id == trip_id, TripModel.user_id == user_id)
            )
        ).first()
        return _record(result) if result is not None else None

    async def create(
        self, user_id: UUID, draft: TripDraft, *, now: datetime, retention_days: int
    ) -> TripRecord:
        row = TripModel(
            id=new_id(),
            user_id=user_id,
            created_at=now,
            updated_at=now,
            expires_at=expires_at(draft.departure_time, retention_days),
        )
        _columns(row, draft)
        async with self._sessions() as session, session.begin():
            session.add(row)
            await _record_consent(session, user_id, draft, now)
            await session.flush()
            loaded = await self._load(session, user_id, row.id)
        assert loaded is not None
        return loaded

    async def get(self, user_id: UUID, trip_id: UUID) -> TripRecord | None:
        async with self._sessions() as session:
            return await self._load(session, user_id, trip_id)

    async def list_trips(
        self, user_id: UUID, *, limit: int, cursor: Cursor | None, status: TripStatus | None
    ) -> list[TripRecord]:
        query = _select().where(TripModel.user_id == user_id)
        if cursor is not None:
            query = query.where(
                tuple_(TripModel.departure_time, TripModel.id) < (cursor.at, cursor.id)
            )
        if status is not None:
            query = query.where(TripModel.status == status.value)
        query = query.order_by(TripModel.departure_time.desc(), TripModel.id.desc()).limit(
            limit + 1
        )
        async with self._sessions() as session:
            return [_record(result) for result in (await session.execute(query)).all()]

    async def update(
        self,
        user_id: UUID,
        trip_id: UUID,
        draft: TripDraft,
        *,
        outdated: bool,
        now: datetime,
        retention_days: int,
    ) -> TripRecord | None:
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(TripModel)
                .where(TripModel.id == trip_id, TripModel.user_id == user_id)
                .with_for_update()
            )
            if row is None:
                return None
            _columns(row, draft)
            row.updated_at = now
            row.expires_at = expires_at(draft.departure_time, retention_days)
            if outdated:
                row.assessment_outdated = True
            await _record_consent(session, user_id, draft, now)
            await session.flush()
            return await self._load(session, user_id, trip_id)

    async def delete(self, user_id: UUID, trip_id: UUID) -> bool:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                delete(TripModel)
                .where(TripModel.id == trip_id, TripModel.user_id == user_id)
                .returning(TripModel.id)
            )
            return result.scalar_one_or_none() is not None

    async def assessments(
        self, user_id: UUID, trip_id: UUID, *, limit: int, cursor: Cursor | None
    ) -> list[RecommendationSummaryRecord] | None:
        model = RecommendationModel
        async with self._sessions() as session:
            owned = await session.scalar(
                select(TripModel.id).where(TripModel.id == trip_id, TripModel.user_id == user_id)
            )
            if owned is None:
                return None
            query = select(model).where(model.trip_id == trip_id, model.user_id == user_id)
            if cursor is not None:
                query = query.where(tuple_(model.created_at, model.id) < (cursor.at, cursor.id))
            query = query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
            return [summary_record(row) for row in (await session.scalars(query)).all()]

    async def conversation_for(self, user_id: UUID, trip_id: UUID) -> UUID | None:
        model = RecommendationModel
        async with self._sessions() as session:
            found: UUID | None = await session.scalar(
                select(model.conversation_id)
                .where(
                    model.trip_id == trip_id,
                    model.user_id == user_id,
                    model.conversation_id.is_not(None),
                )
                .order_by(model.created_at.desc())
                .limit(1)
            )
            return found

    async def due_for_alerts(
        self,
        now: datetime,
        *,
        window: timedelta,
        stale_after: timedelta,
        processing_after: timedelta,
        limit: int,
    ) -> list[DueTrip]:
        running = exists().where(
            RecommendationModel.trip_id == TripModel.id,
            RecommendationModel.status == RecommendationStatus.PROCESSING.value,
            RecommendationModel.created_at > now - processing_after,
        )
        query = (
            select(TripModel.id, TripModel.user_id)
            .join(UserModel, UserModel.id == TripModel.user_id)
            .outerjoin(_LAST, _LAST.id == TripModel.last_recommendation_id)
            .where(
                TripModel.alerts_enabled,
                UserModel.consent_live_alerts,
                UserModel.deleted_at.is_(None),
                TripModel.status.in_(_OPEN),
                TripModel.departure_time > now,
                TripModel.departure_time <= now + window,
                or_(
                    _LAST.id.is_(None),
                    TripModel.assessment_outdated,
                    _LAST.created_at < now - stale_after,
                ),
                ~running,
            )
            .order_by(TripModel.departure_time, TripModel.id)
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.execute(query)).all()
        return [DueTrip(trip_id=trip_id, user_id=user_id) for trip_id, user_id in rows]

    async def user(self, user_id: UUID) -> UserRef | None:
        async with self._sessions() as session:
            row = await session.get(UserModel, user_id)
            return user_ref(row) if row is not None else None
