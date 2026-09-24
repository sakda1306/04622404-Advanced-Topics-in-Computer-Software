"""Finished assessments link back to their trip (D-64) and raise in-app alerts (D-66)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.enums import (
    AgentRunStatus,
    JobStatus,
    MessageRole,
    RecommendationStatus,
    RecommendationType,
    RequestMode,
    RequestSource,
    RiskLevel,
    TravelMode,
)
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.domain.trips import TripDraft
from app.infrastructure.db.models import MessageModel, RecommendationModel
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.infrastructure.db.repositories.trips import SqlTripRepository
from app.services.ports import (
    AgentRunRecord,
    JobOutcome,
    NewRecommendation,
    StoredResult,
    TripRecord,
    UserRef,
)

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)
DRAFT = TripDraft(
    name="North",
    origin=GeoPoint(13.7563, 100.5018, name="Bangkok"),
    destination=GeoPoint(18.7883, 98.9853, name="Chiang Mai"),
    departure_time=NOW + timedelta(days=2),
    timezone="Asia/Bangkok",
    waypoints=(GeoPoint(14.3532, 100.5689, name="Ayutthaya"),),
    preferences=TravelPreferences(travel_modes=(TravelMode.TRAIN,), traveler_count=2),
)


@pytest.fixture
def repo(session_factory: async_sessionmaker[AsyncSession]) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(session_factory)


@pytest.fixture
def trips(session_factory: async_sessionmaker[AsyncSession]) -> SqlTripRepository:
    return SqlTripRepository(session_factory)


async def setup(
    repo: SqlRecommendationRepository, trips: SqlTripRepository
) -> tuple[UserRef, TripRecord]:
    user = await repo.get_or_create_user("iss", f"sub-{uuid4()}", pseudonym=lambda uid: uid.hex)
    trip = await trips.create(user.id, DRAFT, now=NOW, retention_days=30)
    return user, trip


def request_for(draft: TripDraft) -> NormalizedTravelRequest:
    return NormalizedTravelRequest(
        origin=draft.origin,
        destination=draft.destination,
        waypoints=draft.waypoints,
        departure_time=draft.departure_time,
        timezone=draft.timezone,
        language="en",
        preferences=draft.preferences,
        question=None,
    )


def result(risk: RiskLevel = RiskLevel.LOW, message: str = "Looks fine") -> StoredResult:
    return StoredResult(
        status=RecommendationStatus.COMPLETED,
        risk_level=risk,
        risk_score=0.2,
        risk_confidence=0.9,
        recommendation_type=RecommendationType.CHANGE_ROUTE,
        payload={"status": "completed"},
        warning_codes=(),
        applied_rules=(),
        overall_is_stale=False,
        valid_until=None,
        api_version="1.0.0",
        agent_version=None,
        risk_model_version=None,
        prompt_version=None,
        message=message,
    )


async def run(
    repo: SqlRecommendationRepository,
    user: UserRef,
    trip: TripRecord,
    *,
    source: RequestSource = RequestSource.TRIP_ASSESSMENT,
    draft: TripDraft = DRAFT,
    when: datetime = NOW,
    outcome: StoredResult | None = None,
    failed: bool = False,
    conversation_id: UUID | None = None,
) -> UUID:
    created = await repo.create_pending(
        NewRecommendation(
            user_id=user.id,
            request=request_for(draft),
            mode=RequestMode.ASYNC,
            source=source,
            conversation_id=conversation_id,
            trip_id=trip.id,
            cache_key=None,
            correlation_id="corr",
            now=when,
            retention_days=30,
            conversation_days=30,
        )
    )
    assert created.job_id is not None
    await repo.start_job(created.job_id, when, context_messages=10)
    agent = AgentRunRecord(
        new_id(), 1, AgentRunStatus.SUCCESS, 200, None, when, when, 1, None, None
    )
    if failed:
        finished = JobOutcome(JobStatus.FAILED, when, None, "AGENT_TIMEOUT", agent, 30)
    else:
        finished = JobOutcome(JobStatus.SUCCEEDED, when, outcome or result(), None, agent, 30)
    await repo.finish_job(created.job_id, finished)
    return created.recommendation_id


async def conversation_of(repo: SqlRecommendationRepository, recommendation_id: UUID) -> UUID:
    async with repo.sessions() as session:
        found = await session.scalar(
            select(RecommendationModel.conversation_id).where(
                RecommendationModel.id == recommendation_id
            )
        )
    assert found is not None
    return found


async def assistant_messages(repo: SqlRecommendationRepository, conversation_id: UUID) -> int:
    async with repo.sessions() as session:
        count = await session.scalar(
            select(func.count()).where(
                MessageModel.conversation_id == conversation_id,
                MessageModel.role == MessageRole.ASSISTANT.value,
            )
        )
    return int(count or 0)


async def test_finished_assessment_links_the_trip(
    repo: SqlRecommendationRepository, trips: SqlTripRepository
) -> None:
    user, trip = await setup(repo, trips)
    await trips.update(user.id, trip.id, DRAFT, outdated=True, now=NOW, retention_days=30)

    rec = await run(repo, user, trip)

    loaded = await trips.get(user.id, trip.id)
    assert loaded is not None
    assert loaded.last_assessment is not None
    assert loaded.last_assessment.recommendation_id == rec
    assert loaded.last_assessment.risk_level is RiskLevel.LOW
    assert not loaded.assessment_outdated


async def test_result_for_an_old_route_stays_outdated(
    repo: SqlRecommendationRepository, trips: SqlTripRepository
) -> None:
    user, trip = await setup(repo, trips)
    moved = replace(DRAFT, departure_time=DRAFT.departure_time + timedelta(hours=3))
    await trips.update(user.id, trip.id, moved, outdated=True, now=NOW, retention_days=30)

    rec = await run(repo, user, trip, draft=DRAFT)

    loaded = await trips.get(user.id, trip.id)
    assert loaded is not None
    assert loaded.last_assessment is not None
    assert loaded.last_assessment.recommendation_id == rec
    assert loaded.assessment_outdated


@pytest.mark.parametrize(
    "changed",
    [
        replace(DRAFT, origin=GeoPoint(13.8, 100.5)),
        replace(DRAFT, waypoints=()),
        replace(DRAFT, preferences=TravelPreferences()),
    ],
)
async def test_any_route_difference_keeps_outdated(
    repo: SqlRecommendationRepository, trips: SqlTripRepository, changed: TripDraft
) -> None:
    user, trip = await setup(repo, trips)
    await trips.update(user.id, trip.id, changed, outdated=True, now=NOW, retention_days=30)

    await run(repo, user, trip, draft=DRAFT)

    loaded = await trips.get(user.id, trip.id)
    assert loaded is not None
    assert loaded.assessment_outdated


async def test_older_result_does_not_replace_a_newer_link(
    repo: SqlRecommendationRepository, trips: SqlTripRepository
) -> None:
    user, trip = await setup(repo, trips)
    newer = await run(repo, user, trip, when=NOW)

    await run(repo, user, trip, when=NOW - timedelta(minutes=5))

    loaded = await trips.get(user.id, trip.id)
    assert loaded is not None
    assert loaded.last_assessment is not None
    assert loaded.last_assessment.recommendation_id == newer


async def test_failed_job_changes_nothing(
    repo: SqlRecommendationRepository, trips: SqlTripRepository
) -> None:
    user, trip = await setup(repo, trips)
    await trips.update(user.id, trip.id, DRAFT, outdated=True, now=NOW, retention_days=30)

    await run(repo, user, trip, failed=True)

    loaded = await trips.get(user.id, trip.id)
    assert loaded is not None
    assert loaded.last_assessment is None
    assert loaded.assessment_outdated


async def test_alerts_add_a_message_only_when_the_risk_changes(
    repo: SqlRecommendationRepository, trips: SqlTripRepository
) -> None:
    user, trip = await setup(repo, trips)
    first = await run(repo, user, trip, when=NOW - timedelta(hours=3))
    conversation = await conversation_of(repo, first)
    assert await assistant_messages(repo, conversation) == 1

    alert = RequestSource.TRIP_ALERT
    await run(
        repo, user, trip, source=alert, when=NOW - timedelta(hours=2), conversation_id=conversation
    )
    assert await assistant_messages(repo, conversation) == 1

    raised = await run(
        repo,
        user,
        trip,
        source=alert,
        when=NOW - timedelta(hours=1),
        conversation_id=conversation,
        outcome=result(RiskLevel.HIGH, "Heavy rain expected; delay the trip"),
    )
    assert await assistant_messages(repo, conversation) == 2
    async with repo.sessions() as session:
        text = await session.scalar(
            select(MessageModel.content).where(MessageModel.recommendation_id == raised)
        )
    assert text == "Heavy rain expected; delay the trip"
    loaded = await trips.get(user.id, trip.id)
    assert loaded is not None
    assert loaded.last_assessment is not None
    assert loaded.last_assessment.recommendation_id == raised


async def test_first_alert_has_no_message(
    repo: SqlRecommendationRepository, trips: SqlTripRepository
) -> None:
    user, trip = await setup(repo, trips)

    rec = await run(repo, user, trip, source=RequestSource.TRIP_ALERT)

    assert await assistant_messages(repo, await conversation_of(repo, rec)) == 0
    loaded = await trips.get(user.id, trip.id)
    assert loaded is not None
    assert loaded.last_assessment is not None


async def test_deleted_trip_still_stores_the_result(
    repo: SqlRecommendationRepository, trips: SqlTripRepository
) -> None:
    user, trip = await setup(repo, trips)
    created = await repo.create_pending(
        NewRecommendation(
            user_id=user.id,
            request=request_for(DRAFT),
            mode=RequestMode.ASYNC,
            source=RequestSource.TRIP_ASSESSMENT,
            conversation_id=None,
            trip_id=trip.id,
            cache_key=None,
            correlation_id="corr",
            now=NOW,
            retention_days=30,
            conversation_days=30,
        )
    )
    assert created.job_id is not None
    await repo.start_job(created.job_id, NOW, context_messages=10)
    await trips.delete(user.id, trip.id)
    agent = AgentRunRecord(new_id(), 1, AgentRunStatus.SUCCESS, 200, None, NOW, NOW, 1, None, None)

    await repo.finish_job(
        created.job_id, JobOutcome(JobStatus.SUCCEEDED, NOW, result(), None, agent, 30)
    )

    record = await repo.get_recommendation(user.id, created.recommendation_id)
    assert record is not None
    assert record.status is RecommendationStatus.COMPLETED


async def test_cached_result_links_the_trip(
    repo: SqlRecommendationRepository, trips: SqlTripRepository
) -> None:
    user, trip = await setup(repo, trips)

    created = await repo.create_completed(
        NewRecommendation(
            user_id=user.id,
            request=request_for(DRAFT),
            mode=RequestMode.AUTO,
            source=RequestSource.TRIP_ASSESSMENT,
            conversation_id=None,
            trip_id=trip.id,
            cache_key="k" * 64,
            correlation_id="corr",
            now=NOW,
            retention_days=30,
            conversation_days=30,
        ),
        result(),
    )

    loaded = await trips.get(user.id, trip.id)
    assert loaded is not None
    assert loaded.last_assessment is not None
    assert loaded.last_assessment.recommendation_id == created.recommendation_id
