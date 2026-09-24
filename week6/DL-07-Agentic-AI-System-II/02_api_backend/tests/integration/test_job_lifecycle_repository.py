"""Cancel, late results, the reaper and prediction records against PostGIS."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.enums import (
    AgentRunStatus,
    JobStage,
    JobStatus,
    MessageRole,
    RecommendationStatus,
    RecommendationType,
    RequestMode,
    RequestSource,
    RiskLevel,
)
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.domain.prediction import PredictionData
from app.infrastructure.db.models import (
    AgentRunModel,
    JobModel,
    MessageModel,
    PredictionRecordModel,
    RecommendationModel,
    UserModel,
)
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.services.ports import AgentRunRecord, JobOutcome, NewRecommendation, StoredResult, UserRef

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture
def repo(session_factory: async_sessionmaker[AsyncSession]) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(session_factory)


async def make_user(repo: SqlRecommendationRepository, *, analytics: bool = False) -> UserRef:
    user = await repo.get_or_create_user("iss", f"sub-{uuid4()}", pseudonym=lambda uid: uid.hex)
    if analytics:
        async with repo.sessions() as session, session.begin():
            row = await session.get(UserModel, user.id)
            assert row is not None
            row.consent_analytics = True
            row.consent_analytics_at = NOW
    return user


async def pending(
    repo: SqlRecommendationRepository, user: UserRef, *, when: datetime = NOW
) -> tuple[UUID, UUID]:
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
    return created.job_id, created.recommendation_id


def run_record() -> AgentRunRecord:
    return AgentRunRecord(new_id(), 1, AgentRunStatus.SUCCESS, 200, None, NOW, NOW, 1, None, None)


def result() -> StoredResult:
    return StoredResult(
        status=RecommendationStatus.COMPLETED,
        risk_level=RiskLevel.LOW,
        risk_score=0.1,
        risk_confidence=0.9,
        recommendation_type=RecommendationType.CHANGE_ROUTE,
        payload={"status": "completed"},
        warning_codes=(),
        applied_rules=("R-03",),
        overall_is_stale=False,
        valid_until=None,
        api_version="1.0.0",
        agent_version="a-1",
        risk_model_version="r-1",
        prompt_version="p-1",
        message="Go by train",
    )


PREDICTION = PredictionData(
    origin_geohash="w4rqn",
    destination_geohash="w5x0m",
    region_code="TH",
    departure_bucket=NOW.replace(minute=0, second=0),
    lead_time_hours=24,
    travel_modes=("TRAIN",),
    status=RecommendationStatus.COMPLETED,
    risk_level=RiskLevel.LOW,
    risk_score=0.1,
    risk_confidence=0.9,
    recommendation_type=RecommendationType.CHANGE_ROUTE,
    hazard_types=("FLOOD",),
    data_freshness={"overall_is_stale": False},
    service_status={"weather": "ok"},
    safety_gate_rules=("R-03",),
    agent_version="a-1",
    risk_model_version="r-1",
    prompt_version="p-1",
)


def succeeded(prediction: PredictionData | None = None) -> JobOutcome:
    return JobOutcome(
        JobStatus.SUCCEEDED, NOW, result(), None, run_record(), 30, prediction=prediction
    )


async def rows(
    repo: SqlRecommendationRepository, job_id: UUID
) -> tuple[JobModel, RecommendationModel]:
    async with repo.sessions() as session:
        job = await session.get(JobModel, job_id)
        assert job is not None
        rec = await session.get(RecommendationModel, job.recommendation_id)
        assert rec is not None
        return job, rec


# ------------------------------------------------------------------ cancel


async def test_cancel_an_active_job(repo: SqlRecommendationRepository) -> None:
    user, other = await make_user(repo), await make_user(repo)
    job_id, _ = await pending(repo, user)

    assert await repo.cancel_job(other.id, job_id, now=NOW) == (None, None)
    assert await repo.job_cancelled(job_id) is False
    outcome, record = await repo.cancel_job(user.id, job_id, now=NOW)

    assert outcome == "cancelled"
    assert record is not None
    assert record.status is JobStatus.CANCELLED
    assert record.stage is JobStage.CANCELLED
    job, rec = await rows(repo, job_id)
    assert job.cancel_requested_at == NOW
    assert job.finished_at == NOW
    assert rec.status == RecommendationStatus.CANCELLED.value
    assert await repo.job_cancelled(job_id) is True
    again, _ = await repo.cancel_job(user.id, job_id, now=NOW)
    assert again == "not_cancellable"


async def test_a_running_job_can_be_cancelled(repo: SqlRecommendationRepository) -> None:
    user = await make_user(repo)
    job_id, _ = await pending(repo, user)
    await repo.start_job(job_id, NOW, context_messages=10)

    outcome, _ = await repo.cancel_job(user.id, job_id, now=NOW)

    assert outcome == "cancelled"


async def test_finished_job_is_not_cancellable(repo: SqlRecommendationRepository) -> None:
    user = await make_user(repo)
    job_id, _ = await pending(repo, user)
    await repo.start_job(job_id, NOW, context_messages=10)
    assert await repo.finish_job(job_id, succeeded()) is True

    outcome, record = await repo.cancel_job(user.id, job_id, now=NOW)

    assert outcome == "not_cancellable"
    assert record is not None
    assert record.status is JobStatus.SUCCEEDED


async def test_late_result_of_a_cancelled_job_is_discarded(
    repo: SqlRecommendationRepository,
) -> None:
    user = await make_user(repo, analytics=True)
    job_id, rec_id = await pending(repo, user)
    await repo.start_job(job_id, NOW, context_messages=10)
    await repo.cancel_job(user.id, job_id, now=NOW)

    assert await repo.finish_job(job_id, succeeded(PREDICTION)) is False

    job, rec = await rows(repo, job_id)
    assert job.status == JobStatus.CANCELLED.value
    assert rec.status == RecommendationStatus.CANCELLED.value
    assert rec.payload is None
    async with repo.sessions() as session:
        assistant = await session.scalar(
            select(func.count()).where(
                MessageModel.recommendation_id == rec_id,
                MessageModel.role == MessageRole.ASSISTANT.value,
            )
        )
        runs = await session.scalar(
            select(func.count()).select_from(AgentRunModel).where(AgentRunModel.job_id == job_id)
        )
        predictions = await session.scalar(
            select(func.count()).where(PredictionRecordModel.recommendation_id == rec_id)
        )
    assert assistant == 0
    assert runs == 1
    assert predictions == 0


# ------------------------------------------------------------------ reaper


async def test_reaper_fails_only_old_active_jobs(repo: SqlRecommendationRepository) -> None:
    user = await make_user(repo)
    stuck, _ = await pending(repo, user, when=NOW - timedelta(minutes=10))
    running, _ = await pending(repo, user, when=NOW - timedelta(minutes=10))
    await repo.start_job(running, NOW - timedelta(minutes=9), context_messages=10)
    fresh, _ = await pending(repo, user, when=NOW)
    done, _ = await pending(repo, user, when=NOW - timedelta(minutes=10))
    await repo.start_job(done, NOW, context_messages=10)
    await repo.finish_job(done, succeeded())

    reaped = await repo.reap_stuck_jobs(older_than=NOW - timedelta(minutes=2), now=NOW, limit=1000)

    ids = {job.id for job in reaped}
    assert {stuck, running} <= ids
    assert fresh not in ids
    assert done not in ids
    for job_id in (stuck, running):
        job, rec = await rows(repo, job_id)
        assert job.status == JobStatus.FAILED.value
        assert job.error_code == "AGENT_TIMEOUT"
        assert rec.status == RecommendationStatus.FAILED.value
    record = next(job for job in reaped if job.id == stuck)
    assert record.status is JobStatus.FAILED
    assert record.user_id == user.id
    assert await repo.finish_job(stuck, succeeded()) is False


# ------------------------------------------------------------------ prediction records


async def test_prediction_is_stored_only_with_consent(repo: SqlRecommendationRepository) -> None:
    agreed = await make_user(repo, analytics=True)
    declined = await make_user(repo)
    with_consent, rec_yes = await pending(repo, agreed)
    without, rec_no = await pending(repo, declined)
    for job_id in (with_consent, without):
        await repo.start_job(job_id, NOW, context_messages=10)
        assert await repo.finish_job(job_id, succeeded(PREDICTION)) is True

    async with repo.sessions() as session:
        stored = await session.scalar(
            select(PredictionRecordModel).where(PredictionRecordModel.recommendation_id == rec_yes)
        )
        missing = await session.scalar(
            select(PredictionRecordModel.id).where(
                PredictionRecordModel.recommendation_id == rec_no
            )
        )
    assert stored is not None
    assert missing is None
    assert stored.origin_geohash == "w4rqn"
    assert stored.region_code == "TH"
    assert stored.travel_modes == ["TRAIN"]
    assert stored.hazard_types == ["FLOOD"]
    assert stored.safety_gate_rules == ["R-03"]
    assert stored.status == "completed"
    assert stored.risk_level == "LOW"
    assert stored.recommendation_type == "CHANGE_ROUTE"
    assert stored.risk_model_version == "r-1"
    assert stored.created_at == NOW
    assert stored.expires_at == NOW + timedelta(days=365)
