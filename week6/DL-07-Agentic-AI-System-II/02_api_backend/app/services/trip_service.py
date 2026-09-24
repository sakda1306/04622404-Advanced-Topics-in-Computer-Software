"""Saved trips and their assessments (docs/02_api_spec.md section 7.2).

An assessment is a normal recommendation request built from the trip, so validation, the
job queue, the Safety Gate and SSE are the same as for E-01 (D-63).
"""

from __future__ import annotations

from uuid import UUID

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.domain.enums import RequestMode, RequestSource, TripStatus
from app.domain.errors import FieldIssue, InvalidInput
from app.domain.normalization import NormalizationLimits, TravelRequestInput
from app.domain.trips import (
    TripChanges,
    TripDraft,
    apply_trip_changes,
    is_closed,
    route_changed,
    validate_trip,
)
from app.services.pagination import Cursor, Page, build_page, decode_cursor, page_limit
from app.services.ports import RecommendationSummaryRecord, TripRecord, TripRepository, UserRef
from app.services.recommendation_service import (
    CreateOutcome,
    CreateRecommendation,
    RecommendationService,
)

log = get_logger(__name__)


class TripService:
    def __init__(
        self,
        *,
        trips: TripRepository,
        recommendations: RecommendationService,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = trips
        self._recommendations = recommendations
        self._settings = settings
        self._clock = clock

    def _limits(self) -> NormalizationLimits:
        limits = self._settings.limits
        return NormalizationLimits(
            max_waypoints=limits.max_waypoints,
            max_days_ahead=self._settings.trips.max_trip_days_ahead,
            max_question_chars=limits.max_question_chars,
            min_distance_m=limits.min_route_distance_meters,
        )

    @property
    def _retention_days(self) -> int:
        return self._settings.retention.retention_trip_days_after_departure

    async def create(self, user: UserRef, draft: TripDraft) -> TripRecord:
        now = self._clock.now()
        checked = validate_trip(draft, now=now, limits=self._limits(), check_departure_window=True)
        created = await self._repo.create(
            user.id, checked, now=now, retention_days=self._retention_days
        )
        log.info("trip_created", trip_id=str(created.id), alerts=checked.alerts.enabled)
        return created

    async def get(self, user: UserRef, trip_id: UUID) -> TripRecord:
        found = await self._repo.get(user.id, trip_id)
        if found is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return found

    async def list(
        self, user: UserRef, *, limit: int | None, cursor: str | None, status: TripStatus | None
    ) -> Page[TripRecord]:
        size = page_limit(limit, maximum=self._settings.limits.max_page_size)
        rows = await self._repo.list_trips(
            user.id, limit=size, cursor=decode_cursor(cursor), status=status
        )
        return build_page(rows, size, key=lambda row: Cursor(row.draft.departure_time, row.id))

    async def update(self, user: UserRef, trip_id: UUID, changes: TripChanges) -> TripRecord:
        current = await self.get(user, trip_id)
        now = self._clock.now()
        updated = apply_trip_changes(current.draft, changes, now=now, limits=self._limits())
        saved = await self._repo.update(
            user.id,
            trip_id,
            updated,
            outdated=route_changed(current.draft, updated),
            now=now,
            retention_days=self._retention_days,
        )
        if saved is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return saved

    async def delete(self, user: UserRef, trip_id: UUID) -> None:
        if not await self._repo.delete(user.id, trip_id):
            raise AppError(ErrorCode.NOT_FOUND)
        log.info("trip_deleted", trip_id=str(trip_id))

    async def assess(
        self,
        user: UserRef,
        trip_id: UUID,
        *,
        mode: RequestMode,
        language: str | None,
        accept_language: str | None,
        correlation_id: str,
        source: RequestSource = RequestSource.TRIP_ASSESSMENT,
    ) -> CreateOutcome:
        trip = await self.get(user, trip_id)
        draft = trip.draft
        if is_closed(draft.status):
            raise InvalidInput(
                [FieldIssue("status", "trip_closed", "a completed or cancelled trip")]
            )
        if language is None and accept_language is None:
            language = user.language
        return await self._recommendations.create(
            user,
            CreateRecommendation(
                input=TravelRequestInput(
                    origin=draft.origin,
                    destination=draft.destination,
                    departure_time=draft.departure_time,
                    timezone=draft.timezone,
                    waypoints=draft.waypoints,
                    language=language,
                    accept_language=accept_language,
                    preferences=draft.preferences,
                ),
                mode=mode,
                conversation_id=await self._repo.conversation_for(user.id, trip_id),
                trip_id=trip_id,
                correlation_id=correlation_id,
                source=source,
            ),
        )

    async def assessments(
        self, user: UserRef, trip_id: UUID, *, limit: int | None, cursor: str | None
    ) -> Page[RecommendationSummaryRecord]:
        size = page_limit(limit, maximum=self._settings.limits.max_page_size)
        rows = await self._repo.assessments(
            user.id, trip_id, limit=size, cursor=decode_cursor(cursor)
        )
        if rows is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return build_page(rows, size, key=lambda row: Cursor(row.created_at, row.id))
