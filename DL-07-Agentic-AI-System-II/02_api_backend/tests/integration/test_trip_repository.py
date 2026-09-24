"""SQL for trips against PostGIS."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.enums import (
    AlertChannel,
    MobilityNeed,
    RecommendationStatus,
    RequestMode,
    RequestSource,
    RiskLevel,
    TravelMode,
    TripStatus,
)
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.domain.trips import AlertSettings, TripDraft
from app.infrastructure.db.models import RecommendationModel, TripModel
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.infrastructure.db.repositories.trips import SqlTripRepository
from app.services.pagination import Cursor
from app.services.ports import NewRecommendation, TripRecord, UserRef

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)
BANGKOK = GeoPoint(13.7563, 100.5018, name="Bangkok")
CHIANG_MAI = GeoPoint(18.7883, 98.9853, name="Chiang Mai")
AYUTTHAYA = GeoPoint(14.3532, 100.5689, name="Ayutthaya", place_id="p-1")
WINDOW = timedelta(hours=24)
STALE = timedelta(minutes=60)
PROCESSING = timedelta(minutes=2)


@pytest.fixture
def recommendations(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(session_factory)


@pytest.fixture
def trips(session_factory: async_sessionmaker[AsyncSession]) -> SqlTripRepository:
    return SqlTripRepository(session_factory)


async def make_user(repo: SqlRecommendationRepository) -> UserRef:
    return await repo.get_or_create_user("iss", f"sub-{uuid4()}", pseudonym=lambda uid: uid.hex)


def draft(**changes: object) -> TripDraft:
    base = TripDraft(
        name="North trip",
        origin=BANGKOK,
        destination=CHIANG_MAI,
        departure_time=NOW + timedelta(days=3),
        timezone="Asia/Bangkok",
        waypoints=(AYUTTHAYA,),
        preferences=TravelPreferences(
            travel_modes=(TravelMode.TRAIN,),
            mobility_needs=(MobilityNeed.ELDERLY,),
            max_travel_hours=10,
            traveler_count=2,
        ),
        alerts=AlertSettings(enabled=True, consent_at=NOW, channels=(AlertChannel.IN_APP,)),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


async def assess(
    recommendations: SqlRecommendationRepository,
    user: UserRef,
    trip: TripRecord,
    *,
    when: datetime = NOW,
    status: RecommendationStatus | None = None,
    conversation_id: UUID | None = None,
) -> UUID:
    d = trip.draft
    request = NormalizedTravelRequest(
        origin=d.origin,
        destination=d.destination,
        waypoints=d.waypoints,
        departure_time=d.departure_time,
        timezone=d.timezone,
        language="th",
        preferences=d.preferences,
        question=None,
    )
    created = await recommendations.create_pending(
        NewRecommendation(
            user_id=user.id,
            request=request,
            mode=RequestMode.ASYNC,
            source=RequestSource.TRIP_ASSESSMENT,
            conversation_id=conversation_id,
            trip_id=trip.id,
            cache_key=None,
            correlation_id="corr",
            now=when,
            retention_days=30,
            conversation_days=30,
        )
    )
    if status is not None:
        async with recommendations.sessions() as session, session.begin():
            await session.execute(
                update(RecommendationModel)
                .where(RecommendationModel.id == created.recommendation_id)
                .values(status=status.value, risk_level=RiskLevel.MEDIUM.value, payload={})
            )
    return created.recommendation_id


async def link(
    recommendations: SqlRecommendationRepository, trip_id: UUID, recommendation_id: UUID
) -> None:
    async with recommendations.sessions() as session, session.begin():
        await session.execute(
            update(TripModel)
            .where(TripModel.id == trip_id)
            .values(last_recommendation_id=recommendation_id)
        )


# ------------------------------------------------------------------ CRUD


async def test_create_and_get_round_trip(
    trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)

    created = await trips.create(user.id, draft(), now=NOW, retention_days=30)

    assert created.draft == draft()
    assert created.last_assessment is None
    assert not created.assessment_outdated
    assert created.created_at == created.updated_at == NOW
    assert await trips.get(user.id, created.id) == created
    assert await trips.get(other.id, created.id) is None
    async with recommendations.sessions() as session:
        row = await session.get(TripModel, created.id)
        assert row is not None
        assert row.expires_at == draft().departure_time + timedelta(days=30)


async def test_list_by_departure_with_pages_and_status(
    trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    made = [
        await trips.create(
            user.id,
            draft(name=f"t{n}", departure_time=NOW + timedelta(days=n + 1)),
            now=NOW,
            retention_days=30,
        )
        for n in range(3)
    ]
    await trips.create(other.id, draft(), now=NOW, retention_days=30)
    await trips.update(
        user.id,
        made[0].id,
        replace(made[0].draft, status=TripStatus.CANCELLED),
        outdated=False,
        now=NOW,
        retention_days=30,
    )

    first = await trips.list_trips(user.id, limit=2, cursor=None, status=None)
    last = first[1]
    second = await trips.list_trips(
        user.id, limit=2, cursor=Cursor(last.draft.departure_time, last.id), status=None
    )
    cancelled = await trips.list_trips(user.id, limit=5, cursor=None, status=TripStatus.CANCELLED)

    assert [t.draft.name for t in first] == ["t2", "t1", "t0"]
    assert [t.draft.name for t in second] == ["t0"]
    assert [t.draft.name for t in cancelled] == ["t0"]


async def test_update(
    trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    created = await trips.create(user.id, draft(), now=NOW, retention_days=30)
    later = NOW + timedelta(minutes=5)
    changed = replace(
        created.draft,
        name="Changed",
        departure_time=NOW + timedelta(days=5),
        waypoints=(),
        alerts=AlertSettings(),
    )

    assert (
        await trips.update(
            other.id, created.id, changed, outdated=True, now=later, retention_days=30
        )
        is None
    )
    kept = await trips.update(
        user.id, created.id, changed, outdated=False, now=later, retention_days=30
    )
    assert kept is not None
    assert kept.draft == changed
    assert kept.updated_at == later
    assert not kept.assessment_outdated

    marked = await trips.update(
        user.id, created.id, changed, outdated=True, now=later, retention_days=30
    )
    assert marked is not None
    assert marked.assessment_outdated
    again = await trips.update(
        user.id, created.id, changed, outdated=False, now=later, retention_days=30
    )
    assert again is not None
    assert again.assessment_outdated  # False keeps the flag
    async with recommendations.sessions() as session:
        row = await session.get(TripModel, created.id)
        assert row is not None
        assert row.expires_at == changed.departure_time + timedelta(days=30)


async def test_delete_keeps_recommendations(
    trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    trip = await trips.create(user.id, draft(), now=NOW, retention_days=30)
    rec_id = await assess(recommendations, user, trip)

    assert not await trips.delete(other.id, trip.id)
    assert await trips.delete(user.id, trip.id)
    assert not await trips.delete(user.id, trip.id)
    async with recommendations.sessions() as session:
        row = await session.get(RecommendationModel, rec_id)
        assert row is not None
        assert row.trip_id is None


# ------------------------------------------------------------------ assessments


async def test_assessments_and_last_assessment(
    trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    trip = await trips.create(user.id, draft(), now=NOW, retention_days=30)
    other_trip = await trips.create(user.id, draft(), now=NOW, retention_days=30)
    first = await assess(recommendations, user, trip, when=NOW)
    second = await assess(
        recommendations,
        user,
        trip,
        when=NOW + timedelta(minutes=1),
        status=RecommendationStatus.COMPLETED,
    )
    await assess(recommendations, user, other_trip)
    await link(recommendations, trip.id, second)

    items = await trips.assessments(user.id, trip.id, limit=5, cursor=None)
    assert items is not None
    assert [i.id for i in items] == [second, first]
    assert await trips.assessments(other.id, trip.id, limit=5, cursor=None) is None
    page = await trips.assessments(
        user.id, trip.id, limit=1, cursor=Cursor(items[0].created_at, items[0].id)
    )
    assert page is not None
    assert [i.id for i in page] == [first]

    loaded = await trips.get(user.id, trip.id)
    assert loaded is not None
    assert loaded.last_assessment is not None
    assert loaded.last_assessment.recommendation_id == second
    assert loaded.last_assessment.status is RecommendationStatus.COMPLETED
    assert loaded.last_assessment.risk_level is RiskLevel.MEDIUM


async def test_conversation_for(
    trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    trip = await trips.create(user.id, draft(), now=NOW, retention_days=30)
    assert await trips.conversation_for(user.id, trip.id) is None

    first = await assess(recommendations, user, trip)
    async with recommendations.sessions() as session:
        row = await session.get(RecommendationModel, first)
        assert row is not None
        conversation_id = row.conversation_id

    assert await trips.conversation_for(user.id, trip.id) == conversation_id
    assert await trips.conversation_for(other.id, trip.id) is None


async def test_user_lookup(
    trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)
    assert await trips.user(user.id) == user
    assert await trips.user(uuid4()) is None


# ------------------------------------------------------------------ alert scan


async def test_due_for_alerts(
    trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)
    soon = NOW + timedelta(hours=5)

    async def make(**changes: object) -> TripRecord:
        return await trips.create(
            user.id, draft(**({"departure_time": soon} | changes)), now=NOW, retention_days=30
        )

    never = await make(name="never assessed")
    fresh = await make(name="fresh")
    stale = await make(name="stale", departure_time=soon + timedelta(minutes=1))
    outdated = await make(name="outdated", departure_time=soon + timedelta(minutes=2))
    running = await make(name="running")
    await make(name="alerts off", alerts=AlertSettings())
    await make(name="cancelled", status=TripStatus.CANCELLED)
    await make(name="too late", departure_time=NOW + timedelta(hours=30))
    await make(name="departed", departure_time=NOW - timedelta(minutes=1))
    active = await make(name="active", status=TripStatus.ACTIVE)

    done = RecommendationStatus.COMPLETED
    await link(recommendations, fresh.id, await assess(recommendations, user, fresh, status=done))
    old = await assess(recommendations, user, stale, when=NOW - timedelta(hours=2), status=done)
    await link(recommendations, stale.id, old)
    recent = await assess(recommendations, user, outdated, status=done)
    await link(recommendations, outdated.id, recent)
    await trips.update(
        user.id, outdated.id, outdated.draft, outdated=True, now=NOW, retention_days=30
    )
    await assess(recommendations, user, running, when=NOW - timedelta(minutes=1))

    due = await trips.due_for_alerts(
        NOW, window=WINDOW, stale_after=STALE, processing_after=PROCESSING, limit=1000
    )
    mine = [d.trip_id for d in due if d.user_id == user.id]

    assert set(mine) == {never.id, stale.id, outdated.id, active.id}
    assert mine.index(never.id) < mine.index(stale.id) < mine.index(outdated.id)
    limited = await trips.due_for_alerts(
        NOW, window=WINDOW, stale_after=STALE, processing_after=PROCESSING, limit=1
    )
    assert len(limited) == 1


async def test_old_processing_assessment_does_not_block_alerts(
    trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)
    trip = await trips.create(
        user.id, draft(departure_time=NOW + timedelta(hours=2)), now=NOW, retention_days=30
    )
    await assess(recommendations, user, trip, when=NOW - timedelta(minutes=10))

    due = await trips.due_for_alerts(
        NOW, window=WINDOW, stale_after=STALE, processing_after=PROCESSING, limit=1000
    )

    assert trip.id in {d.trip_id for d in due}
