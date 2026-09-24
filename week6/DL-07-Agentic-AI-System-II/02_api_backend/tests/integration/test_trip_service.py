"""Trip use cases, with assessments through the real worker path."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.errors import AppError, ErrorCode
from app.domain.enums import JobType, RecommendationStatus, RequestMode, RequestSource, TripStatus
from app.domain.errors import InvalidInput
from app.domain.normalization import GeoPoint
from app.domain.trips import AlertChanges, AlertSettings, TripChanges, TripDraft
from app.infrastructure.db.models import JobModel, RecommendationModel, TravelRequestModel
from app.services.ports import UserRef
from app.services.recommendation_service import Accepted, Finished
from app.services.trip_service import TripService
from tests.integration.flow import Flow

pytestmark = pytest.mark.integration


def draft(**changes: object) -> TripDraft:
    base = TripDraft(
        name="North trip",
        origin=GeoPoint(13.7563, 100.5018, name="Bangkok"),
        destination=GeoPoint(18.7883, 98.9853, name="Chiang Mai"),
        departure_time=datetime.now(UTC) + timedelta(days=2),
        timezone="Asia/Bangkok",
    )
    return replace(base, **changes)  # type: ignore[arg-type]


async def assess(
    service: TripService, user: UserRef, trip_id: UUID, **options: object
) -> Finished | Accepted:
    values: dict[str, object] = {
        "mode": RequestMode.AUTO,
        "language": None,
        "accept_language": None,
        "correlation_id": "corr-trip",
    }
    values.update(options)
    return await service.assess(user, trip_id, **values)  # type: ignore[arg-type]


async def job_of(flow: Flow, recommendation_id: UUID) -> tuple[str, str, str]:
    async with flow.repo.sessions() as session:
        row = (
            await session.execute(
                select(JobModel.type, TravelRequestModel.source, TravelRequestModel.language)
                .join(RecommendationModel, RecommendationModel.id == JobModel.recommendation_id)
                .join(TravelRequestModel, TravelRequestModel.id == RecommendationModel.request_id)
                .where(RecommendationModel.id == recommendation_id)
            )
        ).one()
    return row[0], row[1], row[2]


async def test_crud(flow: Flow) -> None:
    user, other = await flow.user(), await flow.user()
    service = flow.trips()

    created = await service.create(
        user,
        draft(name=" North ", alerts=AlertSettings(enabled=True, consent_at=datetime.now(UTC))),
    )
    assert created.draft.name == "North"
    assert created.draft.alerts.enabled
    assert await service.get(user, created.id) == created

    page = await service.list(user, limit=None, cursor=None, status=None)
    assert [t.id for t in page.items] == [created.id]
    assert page.next_cursor is None

    renamed = await service.update(user, created.id, TripChanges(name="Renamed"))
    assert renamed.draft.name == "Renamed"
    assert not renamed.assessment_outdated

    for call in (
        service.get(other, created.id),
        service.update(other, created.id, TripChanges(name="x")),
        service.delete(other, created.id),
        service.assessments(other, created.id, limit=None, cursor=None),
    ):
        with pytest.raises(AppError) as info:
            await call
        assert info.value.code is ErrorCode.NOT_FOUND

    await service.delete(user, created.id)
    with pytest.raises(AppError):
        await service.get(user, created.id)


async def test_create_validates(flow: Flow) -> None:
    user = await flow.user()
    with pytest.raises(InvalidInput) as info:
        await flow.trips().create(
            user, draft(departure_time=datetime.now(UTC) + timedelta(days=120))
        )
    assert info.value.issues[0].field == "departure_time"
    # Further ahead than an assessment allows (P-43) is fine for a saved trip (P-55).
    far = await flow.trips().create(
        user, draft(departure_time=datetime.now(UTC) + timedelta(days=60))
    )
    assert far.draft.name == "North trip"


async def test_assess_links_the_trip_and_reuses_the_conversation(flow: Flow) -> None:
    user = await flow.user()
    service = flow.trips()
    trip = await service.create(user, draft())

    first = await assess(service, user, trip.id)
    await flow.queue.drain()

    assert isinstance(first, Finished)
    assert first.record.status is RecommendationStatus.COMPLETED
    assert await job_of(flow, first.record.id) == (
        JobType.TRIP_ASSESSMENT.value,
        RequestSource.TRIP_ASSESSMENT.value,
        "th",
    )
    loaded = await service.get(user, trip.id)
    assert loaded.last_assessment is not None
    assert loaded.last_assessment.recommendation_id == first.record.id
    assert not loaded.assessment_outdated

    moved = await service.update(
        user, trip.id, TripChanges(departure_time=trip.draft.departure_time + timedelta(hours=2))
    )
    assert moved.assessment_outdated

    second = await assess(service, user, trip.id, language="en")
    await flow.queue.drain()
    assert isinstance(second, Finished)
    assert second.record.conversation_id == first.record.conversation_id
    refreshed = await service.get(user, trip.id)
    assert not refreshed.assessment_outdated

    history = await service.assessments(user, trip.id, limit=1, cursor=None)
    assert [r.id for r in history.items] == [second.record.id]
    assert history.next_cursor is not None
    older = await service.assessments(user, trip.id, limit=1, cursor=history.next_cursor)
    assert [r.id for r in older.items] == [first.record.id]


async def test_assess_language_and_async_mode(flow: Flow) -> None:
    user = await flow.user()
    service = flow.trips()
    trip = await service.create(user, draft())

    accepted = await assess(service, user, trip.id, mode=RequestMode.ASYNC, accept_language="en")
    await flow.queue.drain()

    assert isinstance(accepted, Accepted)
    assert (await job_of(flow, accepted.recommendation_id))[2] == "en"


async def test_assess_checks_the_forecast_window(flow: Flow) -> None:
    user = await flow.user()
    service = flow.trips()
    trip = await service.create(user, draft(departure_time=datetime.now(UTC) + timedelta(days=30)))

    with pytest.raises(InvalidInput) as info:
        await assess(service, user, trip.id)

    assert {(i.field, i.code) for i in info.value.issues} == {("departure_time", "too_far_ahead")}


async def test_closed_trip_cannot_be_assessed_or_changed(flow: Flow) -> None:
    user = await flow.user()
    service = flow.trips()
    trip = await service.create(user, draft())
    await service.update(user, trip.id, TripChanges(status=TripStatus.CANCELLED))

    with pytest.raises(InvalidInput) as info:
        await assess(service, user, trip.id)
    assert info.value.issues[0].code == "trip_closed"
    with pytest.raises(InvalidInput):
        await service.update(user, trip.id, TripChanges(alerts=AlertChanges(enabled=False)))


async def test_list_filters_by_status(flow: Flow) -> None:
    user = await flow.user()
    service = flow.trips()
    kept = await service.create(user, draft(name="kept"))
    done = await service.create(user, draft(name="done"))
    await service.update(user, done.id, TripChanges(status=TripStatus.COMPLETED))

    page = await service.list(user, limit=10, cursor=None, status=TripStatus.PLANNED)

    assert [t.id for t in page.items] == [kept.id]
