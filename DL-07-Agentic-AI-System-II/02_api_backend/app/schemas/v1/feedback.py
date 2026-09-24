"""API contract for feedback (spec 7.3) and the safety review queue (spec 8.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import FeedbackOutcome, ReportType, ReviewStatus
from app.domain.feedback import FeedbackInput, ReviewDecision
from app.services.ports import FeedbackRecord, ReviewItem


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeedbackCreate(_Strict):
    rating: int | None = None
    helpful: bool | None = None
    outcome: FeedbackOutcome = FeedbackOutcome.UNKNOWN
    report_type: ReportType | None = None
    # The business limit (1,000 characters) is checked after cleaning.
    comment: str | None = Field(default=None, max_length=20_000)

    def to_domain(self) -> FeedbackInput:
        return FeedbackInput(
            rating=self.rating,
            helpful=self.helpful,
            outcome=self.outcome,
            report_type=self.report_type,
            comment=self.comment,
        )


class FeedbackCreated(_Strict):
    feedback_id: UUID
    created_at: datetime
    review_status: ReviewStatus

    @classmethod
    def from_record(cls, record: FeedbackRecord) -> FeedbackCreated:
        return cls(
            feedback_id=record.id,
            created_at=record.created_at,
            review_status=record.review_status,
        )


class ReviewUpdate(_Strict):
    status: ReviewDecision
    note: str | None = Field(default=None, max_length=20_000)


class ReviewResponse(_Strict):
    feedback_id: UUID
    recommendation_id: UUID
    rating: int | None
    helpful: bool | None
    outcome: FeedbackOutcome
    report_type: ReportType | None
    comment: str | None
    review_status: ReviewStatus
    review_note: str | None
    reviewed_at: datetime | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: FeedbackRecord) -> ReviewResponse:
        return cls(
            feedback_id=record.id,
            recommendation_id=record.recommendation_id,
            rating=record.rating,
            helpful=record.helpful,
            outcome=record.outcome,
            report_type=record.report_type,
            comment=record.comment,
            review_status=record.review_status,
            review_note=record.review_note,
            reviewed_at=record.reviewed_at,
            created_at=record.created_at,
        )


class ReviewQueueItem(ReviewResponse):
    # The sanitized recommendation the report is about (null once it was deleted).
    recommendation: dict[str, Any] | None

    @classmethod
    def from_item(cls, item: ReviewItem) -> ReviewQueueItem:
        base = ReviewResponse.from_record(item.feedback)
        return cls(**base.model_dump(), recommendation=item.recommendation)


class ReviewPage(_Strict):
    items: list[ReviewQueueItem]
    next_cursor: str | None
