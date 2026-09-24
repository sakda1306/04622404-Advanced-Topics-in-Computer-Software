"""Safety review queue for reported feedback (docs/02_api_spec.md section 8.2, D-69)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_feedback_service
from app.api.v1.admin.access import admin_actor
from app.core.security import Scope
from app.domain.enums import ReviewStatus
from app.schemas.v1.feedback import ReviewPage, ReviewQueueItem, ReviewResponse, ReviewUpdate
from app.services.admin_service import Actor
from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/admin/feedback/reviews", tags=["admin"])


@router.get("", summary="Feedback waiting for review, oldest first", response_model=ReviewPage)
async def list_reviews(
    status: ReviewStatus = Query(default=ReviewStatus.PENDING),
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=200),
    actor: Actor = Depends(admin_actor(Scope.SAFETY_REVIEW, "feedback.review_list")),
    service: FeedbackService = Depends(get_feedback_service),
) -> ReviewPage:
    page = await service.reviews(
        actor.subject,
        status=status,
        limit=limit,
        cursor=cursor,
        correlation_id=actor.correlation_id,
        ip_hash=actor.ip_hash,
    )
    return ReviewPage(
        items=[ReviewQueueItem.from_item(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.patch(
    "/{feedback_id}", summary="Approve or reject reported feedback", response_model=ReviewResponse
)
async def review_feedback(
    feedback_id: UUID,
    body: ReviewUpdate,
    actor: Actor = Depends(admin_actor(Scope.SAFETY_REVIEW, "feedback.review")),
    service: FeedbackService = Depends(get_feedback_service),
) -> ReviewResponse:
    record = await service.review(
        actor.subject,
        feedback_id,
        decision=body.status,
        note=body.note,
        correlation_id=actor.correlation_id,
        ip_hash=actor.ip_hash,
    )
    return ReviewResponse.from_record(record)
