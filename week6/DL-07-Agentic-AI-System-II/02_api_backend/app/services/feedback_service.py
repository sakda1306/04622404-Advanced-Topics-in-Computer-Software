"""Feedback on recommendations and the safety review queue (spec sections 7.3 and 8.2).

Feedback is stored under the user's pseudonym. Reports that may describe unsafe or wrong
advice wait for a reviewer; Ops learn about them from the log event and the audit log
(D-68). Every reviewer action is audited (D-69).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.metrics import SAFETY_REVIEWS
from app.domain.enums import ActorType, AuditResult, RecommendationStatus, ReviewStatus
from app.domain.errors import FieldIssue, InvalidInput
from app.domain.feedback import (
    FeedbackInput,
    ReviewDecision,
    check_feedback,
    check_review_note,
    review_status_for,
)
from app.services.pagination import Cursor, Page, build_page, decode_cursor, page_limit
from app.services.ports import (
    AuditEntry,
    AuditPort,
    FeedbackRecord,
    FeedbackRepository,
    RecommendationRepository,
    ReviewItem,
    UserRef,
)

log = get_logger(__name__)

_TARGET = "feedback"


class FeedbackService:
    def __init__(
        self,
        *,
        feedback: FeedbackRepository,
        recommendations: RecommendationRepository,
        audit: AuditPort,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._repo = feedback
        self._recommendations = recommendations
        self._audit = audit
        self._settings = settings
        self._clock = clock

    async def submit(
        self,
        user: UserRef,
        recommendation_id: UUID,
        raw: FeedbackInput,
        *,
        correlation_id: str,
        ip_hash: str | None,
    ) -> FeedbackRecord:
        status = await self._recommendations.feedback_target(user.id, recommendation_id)
        if status is None:
            raise AppError(ErrorCode.NOT_FOUND)
        issues: list[FieldIssue] = []
        if status is RecommendationStatus.PROCESSING:
            issues.append(
                FieldIssue("recommendation_id", "not_finished", "the recommendation is not ready")
            )
        try:
            feedback = check_feedback(raw)
        except InvalidInput as exc:
            raise InvalidInput(issues + exc.issues) from None
        if issues:
            raise InvalidInput(issues)

        review_status = review_status_for(feedback.report_type)
        record = await self._repo.create(
            recommendation_id,
            user.pseudonymous_id,
            feedback,
            review_status=review_status,
            now=self._clock.now(),
            retention_days=self._settings.retention.retention_feedback_days,
        )
        if review_status is not ReviewStatus.PENDING:
            log.info("feedback_received", feedback_id=str(record.id))
            return record
        assert feedback.report_type is not None
        # The comment may contain personal data; only ids and the report type are logged.
        SAFETY_REVIEWS.labels(report_type=feedback.report_type.value).inc()
        log.warning(
            "safety_review_requested",
            feedback_id=str(record.id),
            recommendation_id=str(recommendation_id),
            report_type=feedback.report_type.value,
        )
        await self._write_audit(
            ActorType.USER,
            user.pseudonymous_id,
            "feedback.report",
            record.id,
            AuditResult.SUCCESS,
            correlation_id,
            ip_hash,
            {"report_type": feedback.report_type.value},
        )
        return record

    async def reviews(
        self,
        reviewer: str,
        *,
        status: ReviewStatus,
        limit: int | None,
        cursor: str | None,
        correlation_id: str,
        ip_hash: str | None,
    ) -> Page[ReviewItem]:
        size = page_limit(limit, maximum=self._settings.limits.max_page_size)
        rows = await self._repo.reviews(status=status, limit=size, cursor=decode_cursor(cursor))
        page = build_page(
            rows, size, key=lambda row: Cursor(row.feedback.created_at, row.feedback.id)
        )
        await self._write_audit(
            ActorType.ADMIN,
            reviewer,
            "feedback.review_list",
            None,
            AuditResult.SUCCESS,
            correlation_id,
            ip_hash,
            {"status": status.value, "count": len(page.items)},
        )
        return page

    async def review(
        self,
        reviewer: str,
        feedback_id: UUID,
        *,
        decision: ReviewDecision,
        note: str | None,
        correlation_id: str,
        ip_hash: str | None,
    ) -> FeedbackRecord:
        cleaned = check_review_note(note)
        result = await self._repo.review(
            feedback_id,
            decision=decision,
            note=cleaned,
            reviewer=reviewer,
            now=self._clock.now(),
        )
        if result is None:
            raise AppError(ErrorCode.NOT_FOUND)
        denied = result == "not_pending"
        await self._write_audit(
            ActorType.ADMIN,
            reviewer,
            "feedback.review",
            feedback_id,
            AuditResult.DENIED if denied else AuditResult.SUCCESS,
            correlation_id,
            ip_hash,
            {"status": decision.value},
        )
        if isinstance(result, str):
            raise AppError(ErrorCode.REVIEW_NOT_PENDING)
        log.info("feedback_reviewed", feedback_id=str(feedback_id), status=decision.value)
        return result

    async def _write_audit(
        self,
        actor_type: ActorType,
        actor_ref: str,
        action: str,
        target: UUID | None,
        result: AuditResult,
        correlation_id: str,
        ip_hash: str | None,
        metadata: dict[str, Any],
    ) -> None:
        await self._audit.write(
            AuditEntry(
                actor_type=actor_type,
                actor_ref=actor_ref,
                action=action,
                target_type=_TARGET if target is not None else None,
                target_id=str(target) if target is not None else None,
                result=result,
                correlation_id=correlation_id,
                ip_hash=ip_hash,
                metadata=metadata,
            )
        )
