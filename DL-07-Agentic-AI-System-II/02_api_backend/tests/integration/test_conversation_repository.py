"""SQL for conversations and messages against PostGIS."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.enums import (
    AgentRunStatus,
    JobStatus,
    JobType,
    MessageRole,
    RecommendationStatus,
    RequestMode,
    RequestSource,
    TravelMode,
)
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.infrastructure.db.models import RecommendationModel
from app.infrastructure.db.repositories.conversations import SqlConversationRepository
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.services.pagination import Cursor
from app.services.ports import (
    AgentRunRecord,
    ConversationRecord,
    JobOutcome,
    NewRecommendation,
    StoredResult,
    UserRef,
)

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture
def recommendations(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(session_factory)


@pytest.fixture
def conversations(session_factory: async_sessionmaker[AsyncSession]) -> SqlConversationRepository:
    return SqlConversationRepository(session_factory)


async def make_user(repo: SqlRecommendationRepository) -> UserRef:
    return await repo.get_or_create_user("iss", f"sub-{uuid4()}", pseudonym=lambda uid: uid.hex)


def travel(question: str | None = None, **changes: object) -> NormalizedTravelRequest:
    base = NormalizedTravelRequest(
        origin=GeoPoint(13.7563, 100.5018, name="Bangkok"),
        destination=GeoPoint(18.7883, 98.9853, name="Chiang Mai"),
        waypoints=(),
        departure_time=NOW + timedelta(days=2),
        timezone="Asia/Bangkok",
        language="th",
        preferences=TravelPreferences(travel_modes=(TravelMode.TRAIN,)),
        question=question,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def new(user: UserRef, conversation_id: object = None, **changes: object) -> NewRecommendation:
    base = NewRecommendation(
        user_id=user.id,
        request=travel(),
        mode=RequestMode.AUTO,
        source=RequestSource.RECOMMENDATION,
        conversation_id=conversation_id,  # type: ignore[arg-type]
        trip_id=None,
        cache_key=None,
        correlation_id="corr",
        now=NOW,
        retention_days=30,
        conversation_days=30,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def result(message: str = "Take the train") -> StoredResult:
    return StoredResult(
        status=RecommendationStatus.COMPLETED,
        risk_level=None,
        risk_score=None,
        risk_confidence=None,
        recommendation_type=None,
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


async def finish(
    repo: SqlRecommendationRepository, job_id: object, *, when: datetime = NOW
) -> None:
    run = AgentRunRecord(new_id(), 1, AgentRunStatus.SUCCESS, 200, None, when, when, 1, None, None)
    await repo.start_job(job_id, when, context_messages=10)  # type: ignore[arg-type]
    await repo.finish_job(
        job_id,  # type: ignore[arg-type]
        JobOutcome(JobStatus.SUCCEEDED, when, result(), None, run, 30),
    )


def cursor_of(record: ConversationRecord) -> Cursor:
    return Cursor(record.updated_at, record.id)


# ------------------------------------------------------------------ conversations


async def test_create_and_get(
    conversations: SqlConversationRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)

    created = await conversations.create(
        user.id, title="Trip north", language="en", now=NOW, retention_days=30
    )

    assert created.title == "Trip north"
    assert created.language == "en"
    assert created.message_count == 0
    assert created.last_recommendation_id is None
    assert created.created_at == NOW
    assert await conversations.get(user.id, created.id) == created
    assert await conversations.get(other.id, created.id) is None


async def test_list_newest_first_with_pages(
    conversations: SqlConversationRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    made = [
        await conversations.create(
            user.id, title=f"c{n}", language="th", now=NOW + timedelta(minutes=n), retention_days=30
        )
        for n in range(3)
    ]
    await conversations.create(other.id, title="other", language="th", now=NOW, retention_days=30)

    first = await conversations.list_conversations(user.id, limit=2, cursor=None)
    second = await conversations.list_conversations(user.id, limit=2, cursor=cursor_of(first[1]))

    assert [c.title for c in first] == ["c2", "c1", "c0"]
    assert [c.title for c in second] == ["c0"]
    assert {c.id for c in made} == {c.id for c in first}


async def test_delete_removes_messages_and_keeps_recommendations(
    conversations: SqlConversationRepository,
    recommendations: SqlRecommendationRepository,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    created = await recommendations.create_pending(new(user, request=travel("Safe?")))

    assert not await conversations.delete(other.id, created.conversation_id)
    assert await conversations.delete(user.id, created.conversation_id)
    assert not await conversations.delete(user.id, created.conversation_id)

    assert await conversations.get(user.id, created.conversation_id) is None
    assert (
        await conversations.messages(user.id, created.conversation_id, limit=5, cursor=None) is None
    )
    async with session_factory() as session:
        row = await session.get(RecommendationModel, created.recommendation_id)
    assert row is not None
    assert row.conversation_id is None


# ------------------------------------------------------------------ messages


async def test_messages_newest_first(
    conversations: SqlConversationRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    first = await recommendations.create_pending(new(user, request=travel("q1")))
    await finish(recommendations, first.job_id)
    later = NOW + timedelta(seconds=5)
    second = await recommendations.create_pending(
        new(user, first.conversation_id, request=travel("q2"), now=later)
    )
    await finish(recommendations, second.job_id, when=later)

    rows = await conversations.messages(user.id, first.conversation_id, limit=3, cursor=None)
    assert rows is not None
    assert len(rows) == 4  # limit + 1: tells the caller another page exists
    page = rows[:3]
    last = page[2]
    rest = await conversations.messages(
        user.id, first.conversation_id, limit=3, cursor=Cursor(last.created_at, last.id)
    )

    assert [(m.role, m.content) for m in page] == [
        (MessageRole.ASSISTANT, "Take the train"),
        (MessageRole.USER, "q2"),
        (MessageRole.ASSISTANT, "Take the train"),
    ]
    assert rest is not None
    assert [(m.role, m.content) for m in rest] == [(MessageRole.USER, "q1")]
    assert page[1].recommendation_id == second.recommendation_id
    assert (
        await conversations.messages(other.id, first.conversation_id, limit=3, cursor=None) is None
    )
    conversation = await conversations.get(user.id, first.conversation_id)
    assert conversation is not None
    assert conversation.message_count == 4
    assert conversation.last_recommendation_id == second.recommendation_id


async def test_reply_for_a_recommendation(
    conversations: SqlConversationRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    created = await recommendations.create_pending(new(user, request=travel("q")))
    await finish(recommendations, created.job_id)

    reply = await conversations.reply_for(user.id, created.recommendation_id)

    assert reply is not None
    assert (reply.role, reply.content) == (MessageRole.ASSISTANT, "Take the train")
    assert reply.conversation_id == created.conversation_id
    assert await conversations.reply_for(other.id, created.recommendation_id) is None


# ------------------------------------------------------------------ last request


async def test_last_request_of_a_conversation(
    conversations: SqlConversationRepository, recommendations: SqlRecommendationRepository
) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    empty = await conversations.create(
        user.id, title=None, language="th", now=NOW, retention_days=30
    )
    first = await recommendations.create_pending(new(user, request=travel("q1")))
    newer = travel("q2", destination=GeoPoint(18.29, 99.49, name="Lampang"))
    await recommendations.create_pending(new(user, first.conversation_id, request=newer))

    loaded = await conversations.last_request(user.id, first.conversation_id)

    assert loaded == replace(newer, question=None)
    assert await conversations.last_request(user.id, empty.id) is None
    assert await conversations.last_request(other.id, first.conversation_id) is None


# ------------------------------------------------------------------ jobs and history


async def test_follow_up_jobs_have_the_message_type(
    recommendations: SqlRecommendationRepository,
) -> None:
    user = await make_user(recommendations)

    created = await recommendations.create_pending(new(user, source=RequestSource.MESSAGE))

    assert created.job_id is not None
    job = await recommendations.get_job(user.id, created.job_id)
    assert job is not None
    assert job.type is JobType.MESSAGE
