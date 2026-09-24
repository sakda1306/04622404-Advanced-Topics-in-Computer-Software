"""SQL for feedback, the safety review queue and the audit log."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.enums import (
    ActorType,
    AuditResult,
    FeedbackOutcome,
    RecommendationStatus,
    ReportType,
    RequestMode,
    RequestSource,
    ReviewStatus,
)
from app.domain.feedback import FeedbackInput, ReviewDecision
from app.domain.normalization import GeoPoint, NormalizedTravelRequest, TravelPreferences
from app.infrastructure.audit import SqlAuditWriter
from app.infrastructure.db.models import AuditLogModel, FeedbackModel, RecommendationModel
from app.infrastructure.db.repositories.feedback import SqlFeedbackRepository
from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
from app.services.pagination import Cursor
from app.services.ports import AuditEntry, NewRecommendation, UserRef

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture
def recommendations(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlRecommendationRepository:
    return SqlRecommendationRepository(session_factory)


@pytest.fixture
def feedback(session_factory: async_sessionmaker[AsyncSession]) -> SqlFeedbackRepository:
    return SqlFeedbackRepository(session_factory)


async def make_user(repo: SqlRecommendationRepository) -> UserRef:
    return await repo.get_or_create_user("iss", f"sub-{uuid4()}", pseudonym=lambda uid: uid.hex)


async def make_recommendation(
    repo: SqlRecommendationRepository, user: UserRef, *, finished: bool = True
) -> UUID:
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
                question=None,
            ),
            mode=RequestMode.ASYNC,
            source=RequestSource.RECOMMENDATION,
            conversation_id=None,
            trip_id=None,
            cache_key=None,
            correlation_id="corr",
            now=NOW,
            retention_days=30,
            conversation_days=30,
        )
    )
    if finished:
        async with repo.sessions() as session, session.begin():
            await session.execute(
                update(RecommendationModel)
                .where(RecommendationModel.id == created.recommendation_id)
                .values(
                    status=RecommendationStatus.COMPLETED.value,
                    payload={"recommendation": {"summary": "Go by train"}},
                )
            )
    return created.recommendation_id


async def add(
    feedback: SqlFeedbackRepository,
    recommendation_id: UUID,
    *,
    status: ReviewStatus = ReviewStatus.PENDING,
    when: datetime = NOW,
    comment: str | None = "The road was flooded",
) -> UUID:
    record = await feedback.create(
        recommendation_id,
        "pseudo-1",
        FeedbackInput(
            rating=1,
            helpful=False,
            outcome=FeedbackOutcome.CHANGED_PLAN,
            report_type=ReportType.UNSAFE_ADVICE,
            comment=comment,
        ),
        review_status=status,
        now=when,
        retention_days=180,
    )
    return record.id


async def test_feedback_target(recommendations: SqlRecommendationRepository) -> None:
    user, other = await make_user(recommendations), await make_user(recommendations)
    done = await make_recommendation(recommendations, user)
    running = await make_recommendation(recommendations, user, finished=False)

    assert await recommendations.feedback_target(user.id, done) is RecommendationStatus.COMPLETED
    assert (
        await recommendations.feedback_target(user.id, running) is RecommendationStatus.PROCESSING
    )
    assert await recommendations.feedback_target(other.id, done) is None
    assert await recommendations.feedback_target(user.id, uuid4()) is None


async def test_create_stores_a_pseudonymous_row(
    feedback: SqlFeedbackRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)
    rec = await make_recommendation(recommendations, user)

    record = await feedback.create(
        rec,
        user.pseudonymous_id,
        FeedbackInput(rating=4, helpful=True, outcome=FeedbackOutcome.FOLLOWED, comment="ok"),
        review_status=ReviewStatus.NOT_REQUIRED,
        now=NOW,
        retention_days=180,
    )

    assert record.recommendation_id == rec
    assert record.rating == 4
    assert record.outcome is FeedbackOutcome.FOLLOWED
    assert record.review_status is ReviewStatus.NOT_REQUIRED
    assert record.created_at == NOW
    async with recommendations.sessions() as session:
        row = await session.get(FeedbackModel, record.id)
        assert row is not None
        assert row.pseudonymous_id == user.pseudonymous_id
        assert row.expires_at == NOW + timedelta(days=180)
        assert row.usable_for_training is False


async def test_review_queue_is_oldest_first_with_pages(
    feedback: SqlFeedbackRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)
    rec = await make_recommendation(recommendations, user)
    # Earlier than anything the other tests in this module create.
    base = NOW - timedelta(days=30)
    first = await add(feedback, rec, when=base)
    second = await add(feedback, rec, when=base + timedelta(minutes=1))
    await add(feedback, rec, status=ReviewStatus.NOT_REQUIRED, when=base)

    page = await feedback.reviews(status=ReviewStatus.PENDING, limit=1, cursor=None)
    assert [item.feedback.id for item in page[:2]] == [first, second]
    assert page[0].recommendation == {"recommendation": {"summary": "Go by train"}}
    assert page[0].feedback.comment == "The road was flooded"

    after = await feedback.reviews(status=ReviewStatus.PENDING, limit=1, cursor=Cursor(base, first))
    assert after[0].feedback.id == second


async def test_review_queue_survives_a_deleted_recommendation(
    feedback: SqlFeedbackRepository, recommendations: SqlRecommendationRepository
) -> None:
    missing = new_id()
    fid = await add(feedback, missing, when=NOW - timedelta(days=60))

    items = await feedback.reviews(status=ReviewStatus.PENDING, limit=50, cursor=None)

    item = next(i for i in items if i.feedback.id == fid)
    assert item.recommendation is None


async def test_review(
    feedback: SqlFeedbackRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)
    rec = await make_recommendation(recommendations, user)
    approved_id = await add(feedback, rec)
    rejected_id = await add(feedback, rec)
    later = NOW + timedelta(hours=1)

    approved = await feedback.review(
        approved_id, decision=ReviewDecision.APPROVED, note="Confirmed", reviewer="rev-1", now=later
    )
    rejected = await feedback.review(
        rejected_id, decision=ReviewDecision.REJECTED, note=None, reviewer="rev-1", now=later
    )

    assert approved is not None
    assert not isinstance(approved, str)
    assert approved.review_status is ReviewStatus.APPROVED
    assert approved.reviewed_at == later
    assert approved.review_note == "Confirmed"
    assert rejected is not None
    assert not isinstance(rejected, str)
    assert rejected.review_status is ReviewStatus.REJECTED
    async with recommendations.sessions() as session:
        rows = {
            row.id: row
            for row in (
                await session.scalars(
                    select(FeedbackModel).where(FeedbackModel.id.in_([approved_id, rejected_id]))
                )
            ).all()
        }
    assert rows[approved_id].usable_for_training is True
    assert rows[approved_id].reviewed_by == "rev-1"
    assert rows[rejected_id].usable_for_training is False

    again = await feedback.review(
        approved_id, decision=ReviewDecision.REJECTED, note=None, reviewer="rev-2", now=later
    )
    assert again == "not_pending"
    assert (
        await feedback.review(
            new_id(), decision=ReviewDecision.APPROVED, note=None, reviewer="r", now=later
        )
        is None
    )


async def test_not_required_feedback_cannot_be_reviewed(
    feedback: SqlFeedbackRepository, recommendations: SqlRecommendationRepository
) -> None:
    user = await make_user(recommendations)
    fid = await add(
        feedback, await make_recommendation(recommendations, user), status=ReviewStatus.NOT_REQUIRED
    )

    result = await feedback.review(
        fid, decision=ReviewDecision.APPROVED, note=None, reviewer="r", now=NOW
    )

    assert result == "not_pending"


async def test_audit_writer_appends(session_factory: async_sessionmaker[AsyncSession]) -> None:
    writer = SqlAuditWriter(session_factory)
    target = str(new_id())

    await writer.write(
        AuditEntry(
            actor_type=ActorType.ADMIN,
            actor_ref="reviewer-1",
            action="feedback.review",
            target_type="feedback",
            target_id=target,
            result=AuditResult.SUCCESS,
            correlation_id="corr-audit",
            ip_hash="a" * 64,
            metadata={"status": "approved"},
        )
    )

    async with session_factory() as session:
        row = await session.scalar(select(AuditLogModel).where(AuditLogModel.target_id == target))
    assert row is not None
    assert row.actor_type == "admin"
    assert row.action == "feedback.review"
    assert row.result == "success"
    assert row.metadata_ == {"status": "approved"}
    assert row.occurred_at is not None
