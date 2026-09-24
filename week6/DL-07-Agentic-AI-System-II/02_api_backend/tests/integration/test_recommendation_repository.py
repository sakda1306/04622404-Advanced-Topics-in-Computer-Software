"""SQL repository of the recommendation flow against PostGIS."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.enums import (
    AgentRunStatus,
    AvoidOption,
    JobStage,
    JobStatus,
    JobType,
    RecommendationStatus,
    RecommendationType,
    RequestMode,
    RequestSource,
    RiskLevel,
    TravelMode,
)
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.infrastructure.db.models import (
    AgentRunModel,
    ConversationModel,
    JobModel,
    MessageModel,
    RecommendationModel,
    TravelRequestModel,
    UserModel,
)
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.services.pagination import Cursor
from app.services.ports import (
    AgentRunRecord,
    JobOutcome,
    NewRecommendation,
    StoredResult,
    UserRef,
)
from tests.integration import factories

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)
BANGKOK = GeoPoint(13.7563, 100.5018, name="Bangkok")
CHIANG_MAI = GeoPoint(18.7883, 98.9853, name="Chiang Mai")


@pytest.fixture
def factory(session_factory: async_sessionmaker[AsyncSession]) -> async_sessionmaker[AsyncSession]:
    return session_factory


@pytest.fixture
def repo(factory: async_sessionmaker[AsyncSession]) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(factory)


async def make_user(repo: SqlRecommendationRepository) -> UserRef:
    return await repo.get_or_create_user(
        "http://testserver/dev-issuer", f"sub-{uuid4()}", pseudonym=lambda uid: f"p-{uid}"
    )


def travel(**changes: object) -> NormalizedTravelRequest:
    base = NormalizedTravelRequest(
        origin=BANGKOK,
        destination=CHIANG_MAI,
        waypoints=(GeoPoint(16.0, 99.5, name="Kamphaeng Phet", place_id="kp-1"),),
        departure_time=NOW + timedelta(days=2),
        timezone="Asia/Bangkok",
        language="th",
        preferences=TravelPreferences(
            travel_modes=(TravelMode.BUS, TravelMode.TRAIN),
            avoid=(AvoidOption.TOLLS,),
            max_travel_hours=12,
            traveler_count=2,
        ),
        question=None,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def new(user: UserRef, **changes: object) -> NewRecommendation:
    base = NewRecommendation(
        user_id=user.id,
        request=travel(),
        mode=RequestMode.AUTO,
        source=RequestSource.RECOMMENDATION,
        conversation_id=None,
        trip_id=None,
        cache_key=None,
        correlation_id="corr-1",
        now=NOW,
        retention_days=30,
        conversation_days=30,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def result(**changes: object) -> StoredResult:
    base = StoredResult(
        status=RecommendationStatus.COMPLETED,
        risk_level=RiskLevel.MEDIUM,
        risk_score=0.5432,
        risk_confidence=0.8,
        recommendation_type=RecommendationType.CHANGE_ROUTE,
        payload={"status": "completed", "recommendation": {"summary": "Take the train"}},
        warning_codes=("LOW_CONFIDENCE",),
        applied_rules=("R-03",),
        overall_is_stale=False,
        valid_until=NOW + timedelta(minutes=10),
        api_version="1.0.0",
        agent_version="a-1",
        risk_model_version="r-1",
        prompt_version="p-1",
        message="Take the train",
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def run_record(attempt: int = 1) -> AgentRunRecord:
    return AgentRunRecord(
        run_id=new_id(),
        attempt=attempt,
        status=AgentRunStatus.SUCCESS,
        http_status=200,
        error_code=None,
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=2),
        tool_calls=6,
        agent_version="a-1",
        trace_id="trace-1",
    )


async def fetch(factory: async_sessionmaker[AsyncSession], model: type, ident: UUID) -> object:
    async with factory() as session:
        return await session.get(model, ident)


# ------------------------------------------------------------------ users, ownership, coverage


async def test_user_is_created_once(repo: SqlRecommendationRepository) -> None:
    seen: list[UUID] = []

    def pseudonym(uid: UUID) -> str:
        seen.append(uid)
        return f"p-{uid}"

    first = await repo.get_or_create_user("iss", "sub-same", pseudonym=pseudonym)
    second = await repo.get_or_create_user("iss", "sub-same", pseudonym=pseudonym)

    assert first == second
    assert first.pseudonymous_id == f"p-{first.id}"
    assert seen[0] == first.id
    assert first.language == "th"


async def test_ownership_checks(
    repo: SqlRecommendationRepository, factory: async_sessionmaker[AsyncSession]
) -> None:
    owner, other = await make_user(repo), await make_user(repo)
    created = await repo.create_pending(new(owner))
    async with factory() as session:
        row = await session.get(UserModel, owner.id)
        assert row is not None
        trip = factories.trip(row)
        session.add(trip)
        await session.commit()

    assert await repo.conversation_exists(owner.id, created.conversation_id)
    assert not await repo.conversation_exists(other.id, created.conversation_id)
    assert await repo.trip_exists(owner.id, trip.id)
    assert not await repo.trip_exists(other.id, trip.id)


async def test_region_lookup(repo: SqlRecommendationRepository) -> None:
    assert await repo.region_for(13.7563, 100.5018) == "TH"
    assert await repo.region_for(35.6895, 139.6917) is None


async def test_emergency_defaults(repo: SqlRecommendationRepository) -> None:
    thai = await repo.emergency_default("TH", "th")

    assert thai is not None
    assert thai["contacts"][0]["phone"] == "191"
    assert await repo.emergency_default("JP", "th") is None


# ------------------------------------------------------------------ create


async def test_create_pending_with_question(
    repo: SqlRecommendationRepository, factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await make_user(repo)

    created = await repo.create_pending(new(user, request=travel(question="ปลอดภัยไหม")))

    assert created.job_id is not None
    chosen = new_id()
    assert (await repo.create_pending(new(user, job_id=chosen))).job_id == chosen
    async with factory() as session:
        conversation = await session.get(ConversationModel, created.conversation_id)
        request = await session.get(TravelRequestModel, created.request_id)
        recommendation = await session.get(RecommendationModel, created.recommendation_id)
        job = await session.get(JobModel, created.job_id)
        messages = (
            await session.scalars(
                select(MessageModel).where(MessageModel.conversation_id == created.conversation_id)
            )
        ).all()
    assert conversation is not None
    assert request is not None
    assert recommendation is not None
    assert job is not None
    assert conversation.title == "Bangkok → Chiang Mai"
    assert conversation.message_count == 1
    assert conversation.last_request_id == created.request_id
    assert conversation.expires_at == NOW + timedelta(days=30)
    assert request.has_question is True
    assert request.expires_at == NOW + timedelta(days=30)
    assert request.correlation_id == "corr-1"
    assert recommendation.status == "processing"
    assert recommendation.origin_name == "Bangkok"
    assert (job.status, job.stage, job.type) == ("queued", "queued", "RECOMMENDATION")
    assert [(m.role, m.content, m.recommendation_id) for m in messages] == [
        ("user", "ปลอดภัยไหม", created.recommendation_id)
    ]


async def test_create_pending_in_existing_conversation(
    repo: SqlRecommendationRepository, factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await make_user(repo)
    first = await repo.create_pending(new(user))

    second = await repo.create_pending(new(user, conversation_id=first.conversation_id))

    assert second.conversation_id == first.conversation_id
    conversation = await fetch(factory, ConversationModel, first.conversation_id)
    assert isinstance(conversation, ConversationModel)
    assert conversation.message_count == 0
    assert conversation.last_request_id == second.request_id


async def test_create_completed_has_no_job(
    repo: SqlRecommendationRepository, factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await make_user(repo)

    created = await repo.create_completed(new(user, cache_key="c" * 64), result())

    assert created.job_id is None
    record = await repo.get_recommendation(user.id, created.recommendation_id)
    assert record is not None
    assert record.status is RecommendationStatus.COMPLETED
    assert record.payload == result().payload
    assert record.job_id is None
    request = await fetch(factory, TravelRequestModel, created.request_id)
    assert isinstance(request, TravelRequestModel)
    assert request.cache_key == "c" * 64


# ------------------------------------------------------------------ reads


async def test_reads_are_scoped_to_the_owner(repo: SqlRecommendationRepository) -> None:
    owner, other = await make_user(repo), await make_user(repo)
    created = await repo.create_pending(new(owner))
    assert created.job_id is not None

    record = await repo.get_recommendation(owner.id, created.recommendation_id)
    job = await repo.get_job(owner.id, created.job_id)

    assert record is not None
    assert record.status is RecommendationStatus.PROCESSING
    assert record.payload is None
    assert record.job_id == created.job_id
    assert job is not None
    assert (job.type, job.status, job.stage, job.progress) == (
        JobType.RECOMMENDATION,
        JobStatus.QUEUED,
        JobStage.QUEUED,
        0,
    )
    assert job.recommendation_id == created.recommendation_id
    assert await repo.get_recommendation(other.id, created.recommendation_id) is None
    assert await repo.get_job(other.id, created.job_id) is None
    assert await repo.get_job(owner.id, new_id()) is None


# ------------------------------------------------------------------ worker


async def test_start_job_loads_the_request(repo: SqlRecommendationRepository) -> None:
    user = await make_user(repo)
    wanted = travel(question="ฝนตกไหม")
    created = await repo.create_pending(new(user, request=wanted, cache_key="k" * 64))
    assert created.job_id is not None

    item = await repo.start_job(created.job_id, NOW, context_messages=10)

    assert item is not None
    assert item.attempt == 1
    assert item.user == user
    assert item.recommendation_id == created.recommendation_id
    assert item.request_id == created.request_id
    assert item.conversation_id == created.conversation_id
    assert item.previous_recommendation_id is None
    assert item.request == wanted
    assert item.context == ()
    assert item.cache_key == "k" * 64
    again = await repo.start_job(created.job_id, NOW, context_messages=10)
    assert again is not None
    assert again.attempt == 2


async def test_start_job_includes_earlier_messages(repo: SqlRecommendationRepository) -> None:
    user = await make_user(repo)
    first = await repo.create_pending(new(user, request=travel(question="q1")))
    assert first.job_id is not None
    await repo.start_job(first.job_id, NOW, context_messages=10)
    await repo.finish_job(
        first.job_id,
        JobOutcome(JobStatus.SUCCEEDED, NOW, result(message="a1"), None, run_record(), 30),
    )
    second = await repo.create_pending(
        new(user, request=travel(question="q2"), conversation_id=first.conversation_id)
    )
    assert second.job_id is not None

    item = await repo.start_job(second.job_id, NOW, context_messages=10)
    limited = await repo.start_job(second.job_id, NOW, context_messages=1)

    assert item is not None
    assert limited is not None
    assert item.request.question == "q2"
    assert item.context == (("user", "q1"), ("assistant", "a1"))
    assert limited.context == (("assistant", "a1"),)
    assert item.previous_recommendation_id == first.recommendation_id


async def test_finished_or_unknown_job_is_not_started(
    repo: SqlRecommendationRepository,
) -> None:
    user = await make_user(repo)
    created = await repo.create_pending(new(user))
    assert created.job_id is not None
    await repo.fail_job(created.job_id, "DEPENDENCY_UNAVAILABLE", NOW)

    assert await repo.start_job(created.job_id, NOW, context_messages=10) is None
    assert await repo.start_job(new_id(), NOW, context_messages=10) is None
    record = await repo.get_recommendation(user.id, created.recommendation_id)
    assert record is not None
    assert record.status is RecommendationStatus.FAILED
    assert record.error_code == "DEPENDENCY_UNAVAILABLE"


async def test_finish_job_success(
    repo: SqlRecommendationRepository, factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await make_user(repo)
    created = await repo.create_pending(new(user, request=travel(question="q")))
    assert created.job_id is not None
    await repo.start_job(created.job_id, NOW, context_messages=10)
    run = run_record()

    await repo.set_task_id(created.job_id, "task-1")
    await repo.finish_job(
        created.job_id,
        JobOutcome(JobStatus.SUCCEEDED, NOW, result(), None, run, 30),
    )

    async with factory() as session:
        recommendation = await session.get(RecommendationModel, created.recommendation_id)
        job = await session.get(JobModel, created.job_id)
        agent_run = await session.get(AgentRunModel, run.run_id)
        conversation = await session.get(ConversationModel, created.conversation_id)
        assistant = await session.scalar(
            select(MessageModel.content).where(
                MessageModel.conversation_id == created.conversation_id,
                MessageModel.role == "assistant",
            )
        )
    assert recommendation is not None
    assert job is not None
    assert agent_run is not None
    assert conversation is not None
    assert recommendation.status == "completed"
    assert recommendation.risk_level == "MEDIUM"
    assert float(recommendation.risk_score or 0) == 0.543
    assert recommendation.recommendation_type == "CHANGE_ROUTE"
    assert recommendation.payload == result().payload
    assert recommendation.warning_codes == ["LOW_CONFIDENCE"]
    assert recommendation.safety_gate_rules == ["R-03"]
    assert recommendation.valid_until == NOW + timedelta(minutes=10)
    assert recommendation.completed_at == NOW
    assert (recommendation.api_version, recommendation.agent_version) == ("1.0.0", "a-1")
    assert (job.status, job.stage, job.progress) == ("succeeded", "completed", 100)
    assert job.celery_task_id == "task-1"
    assert job.finished_at == NOW
    assert (agent_run.job_id, agent_run.status, agent_run.duration_ms) == (
        created.job_id,
        "success",
        2000,
    )
    assert conversation.last_recommendation_id == created.recommendation_id
    assert conversation.message_count == 2
    assert assistant == "Take the train"


async def test_finish_job_failure(
    repo: SqlRecommendationRepository, factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await make_user(repo)
    created = await repo.create_pending(new(user))
    assert created.job_id is not None
    await repo.start_job(created.job_id, NOW, context_messages=10)

    await repo.finish_job(
        created.job_id,
        JobOutcome(JobStatus.FAILED, NOW, None, "AGENT_BAD_RESPONSE", None, 30),
    )

    job = await repo.get_job(user.id, created.job_id)
    record = await repo.get_recommendation(user.id, created.recommendation_id)
    assert job is not None
    assert record is not None
    assert (job.status, job.stage, job.error_code) == (
        JobStatus.FAILED,
        JobStage.FAILED,
        "AGENT_BAD_RESPONSE",
    )
    assert record.status is RecommendationStatus.FAILED
    assert record.error_code == "AGENT_BAD_RESPONSE"
    async with factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(MessageModel)
            .where(MessageModel.conversation_id == created.conversation_id)
        )
    assert count == 0


# ------------------------------------------------------------------ history


async def test_history_is_newest_first_and_paged(repo: SqlRecommendationRepository) -> None:
    user, other = await make_user(repo), await make_user(repo)
    made = []
    for minutes in range(3):
        when = NOW + timedelta(minutes=minutes)
        made.append(await repo.create_pending(new(user, now=when)))
    await repo.create_pending(new(other))

    first = await repo.list_recommendations(
        user.id, limit=2, cursor=None, created_from=None, created_to=None, risk_level=None
    )
    last = first[1]
    rest = await repo.list_recommendations(
        user.id,
        limit=2,
        cursor=Cursor(last.created_at, last.id),
        created_from=None,
        created_to=None,
        risk_level=None,
    )

    assert [s.id for s in first] == [m.recommendation_id for m in reversed(made)]
    assert [s.id for s in rest] == [made[0].recommendation_id]
    summary = first[0]
    assert summary.status is RecommendationStatus.PROCESSING
    assert (summary.origin_name, summary.destination_name) == ("Bangkok", "Chiang Mai")
    assert summary.departure_time == NOW + timedelta(days=2)
    assert summary.risk_level is None


async def test_history_filters(repo: SqlRecommendationRepository) -> None:
    user = await make_user(repo)
    early = await repo.create_pending(new(user, now=NOW - timedelta(days=2)))
    medium = await repo.create_completed(new(user), result())
    high = await repo.create_completed(
        new(user, now=NOW + timedelta(minutes=1)),
        result(risk_level=RiskLevel.HIGH, recommendation_type=RecommendationType.AVOID_TRAVEL),
    )

    async def ids(**filters: Any) -> list[UUID]:
        values: dict[str, Any] = {"created_from": None, "created_to": None, "risk_level": None}
        values.update(filters)
        rows = await repo.list_recommendations(user.id, limit=10, cursor=None, **values)
        return [row.id for row in rows]

    assert await ids(risk_level=RiskLevel.HIGH) == [high.recommendation_id]
    assert await ids(created_from=NOW - timedelta(hours=1)) == [
        high.recommendation_id,
        medium.recommendation_id,
    ]
    assert await ids(created_to=NOW - timedelta(days=1)) == [early.recommendation_id]
    summaries = await repo.list_recommendations(
        user.id, limit=1, cursor=None, created_from=None, created_to=None, risk_level=None
    )
    assert summaries[0].recommendation_type is RecommendationType.AVOID_TRAVEL
