"""Feedback and the safety review queue (docs/03_data_design.md section 3.10).

Rows carry the user's pseudonym only; there is no foreign key to recommendations, so
feedback outlives the recommendation it is about.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.domain.enums import FeedbackOutcome, ReportType, ReviewStatus
from app.domain.feedback import FeedbackInput, ReviewDecision
from app.domain.retention import expires_at
from app.infrastructure.db.models import FeedbackModel, RecommendationModel
from app.services.pagination import Cursor
from app.services.ports import FeedbackRecord, ReviewItem


def _record(row: FeedbackModel) -> FeedbackRecord:
    return FeedbackRecord(
        id=row.id,
        recommendation_id=row.recommendation_id,
        rating=row.rating,
        helpful=row.helpful,
        outcome=FeedbackOutcome(row.outcome),
        report_type=ReportType(row.report_type) if row.report_type else None,
        comment=row.comment,
        review_status=ReviewStatus(row.review_status),
        reviewed_at=row.reviewed_at,
        review_note=row.review_note,
        created_at=row.created_at,
    )


class SqlFeedbackRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(
        self,
        recommendation_id: UUID,
        pseudonymous_id: str,
        feedback: FeedbackInput,
        *,
        review_status: ReviewStatus,
        now: datetime,
        retention_days: int,
    ) -> FeedbackRecord:
        row = FeedbackModel(
            id=new_id(),
            recommendation_id=recommendation_id,
            pseudonymous_id=pseudonymous_id,
            rating=feedback.rating,
            helpful=feedback.helpful,
            outcome=feedback.outcome.value,
            report_type=feedback.report_type.value if feedback.report_type else None,
            comment=feedback.comment,
            review_status=review_status.value,
            usable_for_training=False,
            created_at=now,
            expires_at=expires_at(now, retention_days),
        )
        async with self._sessions() as session, session.begin():
            session.add(row)
        return _record(row)

    async def reviews(
        self, *, status: ReviewStatus, limit: int, cursor: Cursor | None
    ) -> list[ReviewItem]:
        model = FeedbackModel
        query = (
            select(model, RecommendationModel.payload)
            .outerjoin(RecommendationModel, RecommendationModel.id == model.recommendation_id)
            .where(model.review_status == status.value)
        )
        if cursor is not None:
            query = query.where(tuple_(model.created_at, model.id) > (cursor.at, cursor.id))
        query = query.order_by(model.created_at, model.id).limit(limit + 1)
        async with self._sessions() as session:
            rows = (await session.execute(query)).all()
        return [ReviewItem(feedback=_record(row), recommendation=payload) for row, payload in rows]

    async def review(
        self,
        feedback_id: UUID,
        *,
        decision: ReviewDecision,
        note: str | None,
        reviewer: str,
        now: datetime,
    ) -> FeedbackRecord | Literal["not_pending"] | None:
        async with self._sessions() as session, session.begin():
            row = await session.get(FeedbackModel, feedback_id, with_for_update=True)
            if row is None:
                return None
            if row.review_status != ReviewStatus.PENDING.value:
                return "not_pending"
            row.review_status = decision.status.value
            row.reviewed_by = reviewer
            row.reviewed_at = now
            row.review_note = note
            # Only confirmed reports may be used to retrain models (spec section 7.3).
            row.usable_for_training = decision is ReviewDecision.APPROVED
            return _record(row)
