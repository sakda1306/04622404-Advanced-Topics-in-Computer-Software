"""Feedback use cases: submission, safety review routing, reviews and the audit trail."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import select

from app.core.errors import AppError, ErrorCode
from app.domain.enums import FeedbackOutcome, ReportType, RequestMode, ReviewStatus
from app.domain.errors import InvalidInput
from app.domain.feedback import FeedbackInput, ReviewDecision
from app.infrastructure.db.models import AuditLogModel
from app.services.ports import UserRef
from app.services.recommendation_service import CreateRecommendation, Finished
from tests.integration.flow import Flow, travel_input

pytestmark = pytest.mark.integration

UNSAFE = FeedbackInput(
    rating=1, report_type=ReportType.UNSAFE_ADVICE, comment="Sent me into the flood zone"
)


async def finished_recommendation(flow: Flow, user: UserRef, *, wait: bool = True) -> UUID:
    service = flow.recommendations()
    if not wait:
        flow.queue.worker = None
    outcome = await service.create(
        user,
        CreateRecommendation(
            input=travel_input(),
            mode=RequestMode.AUTO if wait else RequestMode.ASYNC,
            conversation_id=None,
            trip_id=None,
            correlation_id="corr-feedback",
        ),
    )
    await flow.queue.drain()
    if isinstance(outcome, Finished):
        return outcome.record.id
    return outcome.recommendation_id


async def submit(flow: Flow, user: UserRef, rec: UUID, raw: FeedbackInput) -> Any:
    return await flow.feedback().submit(user, rec, raw, correlation_id="corr-fb", ip_hash="b" * 64)


async def audit_rows(flow: Flow, target: str) -> list[AuditLogModel]:
    async with flow.repo.sessions() as session:
        return list(
            (
                await session.scalars(
                    select(AuditLogModel)
                    .where(AuditLogModel.target_id == target)
                    .order_by(AuditLogModel.id)
                )
            ).all()
        )


async def test_plain_feedback_needs_no_review(flow: Flow) -> None:
    user = await flow.user()
    rec = await finished_recommendation(flow, user)

    record = await submit(
        flow, user, rec, FeedbackInput(rating=5, helpful=True, outcome=FeedbackOutcome.FOLLOWED)
    )

    assert record.review_status is ReviewStatus.NOT_REQUIRED
    assert await audit_rows(flow, str(record.id)) == []


async def test_unsafe_report_goes_to_the_queue(
    flow: Flow, capsys: pytest.CaptureFixture[str]
) -> None:
    user = await flow.user()
    rec = await finished_recommendation(flow, user)
    capsys.readouterr()
    labels = {"report_type": "UNSAFE_ADVICE"}
    before = REGISTRY.get_sample_value("safety_review_requested_total", labels) or 0.0

    record = await submit(flow, user, rec, UNSAFE)

    assert record.review_status is ReviewStatus.PENDING
    assert REGISTRY.get_sample_value("safety_review_requested_total", labels) == before + 1
    logs = capsys.readouterr().out
    assert "safety_review_requested" in logs
    assert "flood zone" not in logs
    rows = await audit_rows(flow, str(record.id))
    assert [(r.action, r.actor_type, r.actor_ref, r.result) for r in rows] == [
        ("feedback.report", "user", user.pseudonymous_id, "success")
    ]
    assert rows[0].metadata_ == {"report_type": "UNSAFE_ADVICE"}
    assert rows[0].ip_hash == "b" * 64
    assert str(user.id) not in str(rows[0].metadata_)


async def test_missing_or_foreign_recommendation_is_404(flow: Flow) -> None:
    user, other = await flow.user(), await flow.user()
    rec = await finished_recommendation(flow, user)

    for who, target in ((other, rec), (user, uuid4())):
        with pytest.raises(AppError) as info:
            await submit(flow, who, target, UNSAFE)
        assert info.value.code is ErrorCode.NOT_FOUND


async def test_unfinished_recommendation_is_rejected(flow: Flow) -> None:
    user = await flow.user()
    rec = await finished_recommendation(flow, user, wait=False)

    with pytest.raises(InvalidInput) as info:
        await submit(flow, user, rec, FeedbackInput(rating=9))

    assert {(i.field, i.code) for i in info.value.issues} == {
        ("recommendation_id", "not_finished"),
        ("rating", "out_of_range"),
    }


async def test_review_flow_is_audited(flow: Flow) -> None:
    user = await flow.user()
    rec = await finished_recommendation(flow, user)
    record = await submit(flow, user, rec, UNSAFE)
    service = flow.feedback()

    page = await service.reviews(
        "reviewer-1",
        status=ReviewStatus.PENDING,
        limit=50,
        cursor=None,
        correlation_id="corr-list",
        ip_hash=None,
    )
    assert record.id in {item.feedback.id for item in page.items}

    reviewed = await service.review(
        "reviewer-1",
        record.id,
        decision=ReviewDecision.APPROVED,
        note="  Confirmed with the flood map ",
        correlation_id="corr-review",
        ip_hash=None,
    )
    assert reviewed.review_status is ReviewStatus.APPROVED
    assert reviewed.review_note == "Confirmed with the flood map"

    with pytest.raises(AppError) as info:
        await service.review(
            "reviewer-2",
            record.id,
            decision=ReviewDecision.REJECTED,
            note=None,
            correlation_id="corr-again",
            ip_hash=None,
        )
    assert info.value.code is ErrorCode.REVIEW_NOT_PENDING
    with pytest.raises(AppError) as missing:
        await service.review(
            "reviewer-1",
            uuid4(),
            decision=ReviewDecision.APPROVED,
            note=None,
            correlation_id="corr-missing",
            ip_hash=None,
        )
    assert missing.value.code is ErrorCode.NOT_FOUND

    rows = await audit_rows(flow, str(record.id))
    assert [(r.action, r.actor_type, r.actor_ref, r.result) for r in rows] == [
        ("feedback.report", "user", user.pseudonymous_id, "success"),
        ("feedback.review", "admin", "reviewer-1", "success"),
        ("feedback.review", "admin", "reviewer-2", "denied"),
    ]
    assert rows[1].metadata_ == {"status": "approved"}
    async with flow.repo.sessions() as session:
        listed = await session.scalar(
            select(AuditLogModel).where(AuditLogModel.correlation_id == "corr-list")
        )
    assert listed is not None
    assert listed.action == "feedback.review_list"
    assert listed.metadata_["status"] == "pending"


async def test_review_note_is_limited(flow: Flow) -> None:
    with pytest.raises(InvalidInput):
        await flow.feedback().review(
            "reviewer-1",
            uuid4(),
            decision=ReviewDecision.APPROVED,
            note="x" * 1001,
            correlation_id="corr",
            ip_hash=None,
        )
