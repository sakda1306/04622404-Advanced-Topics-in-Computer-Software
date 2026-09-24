"""SQL for the profile, consents and account deletion."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.enums import (
    FeedbackOutcome,
    RecommendationStatus,
    ReportType,
    RequestMode,
    RequestSource,
    ReviewStatus,
)
from app.domain.feedback import FeedbackInput
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.domain.profile import Consents
from app.domain.trips import AlertSettings, TripDraft
from app.infrastructure.db.models import (
    ConversationModel,
    FeedbackModel,
    JobModel,
    PredictionRecordModel,
    RecommendationModel,
    TripModel,
    UserModel,
)
from app.infrastructure.db.repositories.feedback import SqlFeedbackRepository
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.infrastructure.db.repositories.trips import SqlTripRepository
from app.infrastructure.db.repositories.users import SqlUserRepository
from app.services.ports import NewRecommendation, UserRef

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture
def recommendations(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(session_factory)


@pytest.fixture
def users(session_factory: async_sessionmaker[AsyncSession]) -> SqlUserRepository:
    return SqlUserRepository(session_factory)


@pytest.fixture
def trips(session_factory: async_sessionmaker[AsyncSession]) -> SqlTripRepository:
    return SqlTripRepository(session_factory)


async def make_user(repo: SqlRecommendationRepository) -> UserRef:
    return await repo.get_or_create_user("iss", f"sub-{uuid4()}", pseudonym=lambda uid: uid.hex)


def trip_draft(alerts: bool = True) -> TripDraft:
    return TripDraft(
        name="North",
        origin=GeoPoint(13.7563, 100.5018),
        destination=GeoPoint(18.7883, 98.9853),
        departure_time=NOW + timedelta(hours=5),
        timezone="Asia/Bangkok",
        alerts=AlertSettings(enabled=True, consent_at=NOW) if alerts else AlertSettings(),
    )


async def recommend(repo: SqlRecommendationRepository, user: UserRef, when: datetime = NOW) -> UUID:
    created = await repo.create_pending(
        NewRecommendation(
            user_id=user.id,
            request=NormalizedTravelRequest(
                origin=GeoPoint(13.7563, 100.5018),
                destination=GeoPoint(18.7883, 98.9853),
                waypoints=(),
                departure_time=NOW + timedelta(days=1),
                timezone="Asia/Bangkok",
                language="th",
                preferences=TravelPreferences(),
                question="Is it safe?",
            ),
            mode=RequestMode.ASYNC,
            source=RequestSource.RECOMMENDATION,
            conversation_id=None,
            trip_id=None,
            cache_key=None,
            correlation_id="corr",
            now=when,
            retention_days=30,
            conversation_days=30,
        )
    )
    assert created.job_id is not None
    return created.job_id


async def test_profile_round_trip(
    users: SqlUserRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)

    record = await users.profile(user.id)
    assert record is not None
    assert record.user_id == user.id
    assert record.profile.language == "th"
    assert record.profile.consents == Consents(False, None, False, None)

    changed = replace(
        record.profile,
        display_name="Nok",
        language="en",
        home_region="TH-50",
        consents=Consents(False, None, True, NOW),
    )
    saved = await users.update_profile(user.id, changed, now=NOW)
    assert saved is not None
    assert saved.profile == changed
    assert await users.profile(uuid4()) is None
    assert await users.update_profile(uuid4(), changed, now=NOW) is None


async def test_withdrawing_live_alerts_turns_trip_alerts_off(
    users: SqlUserRepository, trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    mine = await trips.create(user.id, trip_draft(), now=NOW, retention_days=30)
    theirs = await trips.create(other.id, trip_draft(), now=NOW, retention_days=30)
    record = await users.profile(user.id)
    assert record is not None
    # Turning alerts on for a trip recorded the user's consent (D-77).
    assert record.profile.consents.live_alerts is True
    assert record.profile.consents.live_alerts_at == NOW

    withdrawn = replace(
        record.profile,
        consents=replace(record.profile.consents, live_alerts=False, live_alerts_at=None),
    )
    await users.update_profile(user.id, withdrawn, now=NOW)

    mine_now = await trips.get(user.id, mine.id)
    theirs_now = await trips.get(other.id, theirs.id)
    assert mine_now is not None
    assert mine_now.draft.alerts == AlertSettings()
    assert theirs_now is not None
    assert theirs_now.draft.alerts.enabled is True


async def test_scan_needs_the_users_consent(
    users: SqlUserRepository, trips: SqlTripRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)
    trip = await trips.create(user.id, trip_draft(), now=NOW, retention_days=30)
    async with recommendations.sessions() as session, session.begin():
        row = await session.get(UserModel, user.id)
        assert row is not None
        row.consent_live_alerts = False

    due = await trips.due_for_alerts(
        NOW,
        window=timedelta(hours=24),
        stale_after=timedelta(hours=1),
        processing_after=timedelta(minutes=2),
        limit=1000,
    )

    assert trip.id not in {d.trip_id for d in due}


async def test_request_deletion(
    users: SqlUserRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)

    assert await users.request_deletion(user.id, now=NOW) is True
    assert await users.request_deletion(user.id, now=NOW) is False
    again = await recommendations.get_or_create_user(
        "iss", (await _subject(recommendations, user.id)), pseudonym=lambda uid: uid.hex
    )
    assert again.deletion_requested is True
    assert user.deletion_requested is False


async def _subject(repo: SqlRecommendationRepository, user_id: UUID) -> str:
    async with repo.sessions() as session:
        subject = await session.scalar(
            select(UserModel.oidc_subject).where(UserModel.id == user_id)
        )
    assert subject is not None
    return subject


async def test_recent_job_ids(
    users: SqlUserRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    recent = await recommend(recommendations, user)
    await recommend(recommendations, user, when=NOW - timedelta(days=2))
    await recommend(recommendations, other)

    found = await users.recent_job_ids(user.id, since=NOW - timedelta(hours=24))

    assert found == [recent]


async def test_delete_account(
    users: SqlUserRepository,
    trips: SqlTripRepository,
    recommendations: SqlRecommendationRepository,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    await trips.create(user.id, trip_draft(), now=NOW, retention_days=30)
    job_id = await recommend(recommendations, user)
    await recommend(recommendations, other)
    async with recommendations.sessions() as session:
        rec_id = await session.scalar(
            select(JobModel.recommendation_id).where(JobModel.id == job_id)
        )
    assert rec_id is not None
    async with recommendations.sessions() as session, session.begin():
        await session.execute(
            update(RecommendationModel)
            .where(RecommendationModel.id == rec_id)
            .values(status=RecommendationStatus.COMPLETED.value, payload={})
        )
        session.add(
            PredictionRecordModel(
                id=new_id(),
                recommendation_id=rec_id,
                origin_geohash="w4rqn",
                destination_geohash="w5x0m",
                departure_bucket=NOW,
                lead_time_hours=24,
                travel_modes=[],
                status="completed",
                hazard_types=[],
                data_freshness={},
                service_status={},
                safety_gate_rules=[],
                created_at=NOW,
                expires_at=NOW + timedelta(days=365),
            )
        )
    feedback = await SqlFeedbackRepository(session_factory).create(
        rec_id,
        user.pseudonymous_id,
        FeedbackInput(
            rating=1,
            outcome=FeedbackOutcome.IGNORED,
            report_type=ReportType.OTHER,
            comment="my street",
        ),
        review_status=ReviewStatus.NOT_REQUIRED,
        now=NOW,
        retention_days=180,
    )

    assert await users.delete_account(user.id) == user.pseudonymous_id
    assert await users.delete_account(user.id) is None

    async with recommendations.sessions() as session:
        assert await session.get(UserModel, user.id) is None
        for model in (ConversationModel, TripModel, RecommendationModel, JobModel):
            count = await session.scalar(
                select(func.count()).select_from(model).where(model.user_id == user.id)
            )
            assert count == 0, model.__tablename__
        kept = await session.get(FeedbackModel, feedback.id)
        assert kept is not None
        assert kept.comment is None
        assert kept.pseudonymous_id == "deleted"
        assert await session.scalar(
            select(PredictionRecordModel.id).where(
                PredictionRecordModel.recommendation_id == rec_id
            )
        )
        assert await session.get(UserModel, other.id) is not None


async def test_pending_deletions(
    users: SqlUserRepository, recommendations: SqlRecommendationRepository
) -> None:
    old, fresh = await make_user(recommendations), await make_user(recommendations)
    await users.request_deletion(old.id, now=NOW - timedelta(minutes=30))
    await users.request_deletion(fresh.id, now=NOW)

    pending = await users.pending_deletions(older_than=NOW - timedelta(minutes=10), limit=1000)

    assert old.id in pending
    assert fresh.id not in pending
