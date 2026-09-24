"""Admin queries and training exports against PostGIS (docs/02_api_spec.md 8.2, D-92..D-95)."""

from __future__ import annotations

import gzip
import json
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, update

from app.core.errors import AppError
from app.domain.admin import AuditFilter
from app.domain.enums import (
    ExportStatus,
    FeedbackOutcome,
    JobStatus,
    JobType,
    ReportType,
    RequestMode,
)
from app.domain.feedback import FeedbackInput, ReviewDecision
from app.infrastructure.db.models import (
    JobModel,
    PredictionRecordModel,
    TrainingExportModel,
    UserModel,
)
from app.services.admin_service import Actor
from app.services.ports import AdminRecommendationRecord, UserRef
from app.services.recommendation_service import CreateRecommendation, Finished
from tests.integration.flow import Flow, travel_input

pytestmark = pytest.mark.integration

ADMIN = Actor("admin-1", "corr-admin", "c" * 64)
HOUR = timedelta(hours=1)


async def recommend(flow: Flow, user: UserRef, question: str) -> UUID:
    outcome = await flow.recommendations().create(
        user,
        CreateRecommendation(
            input=travel_input(question=question),
            mode=RequestMode.AUTO,
            conversation_id=None,
            trip_id=None,
            correlation_id="corr-admin-test",
        ),
    )
    await flow.queue.drain()
    assert isinstance(outcome, Finished)
    return outcome.record.id


async def with_analytics(flow: Flow, user: UserRef) -> None:
    async with flow.repo.sessions() as session, session.begin():
        await session.execute(
            update(UserModel).where(UserModel.id == user.id).values(consent_analytics=True)
        )


def window() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    return now - HOUR, now + HOUR


async def test_jobs_listing_is_bounded_filtered_and_paged(flow: Flow) -> None:
    user = await flow.user()
    for n in range(3):
        await recommend(flow, user, f"question {n}")
    # One job moves out of the window: the listing must not return it.
    one_job = select(JobModel.id).where(JobModel.user_id == user.id).limit(1)
    async with flow.repo.sessions() as session, session.begin():
        await session.execute(
            update(JobModel)
            .where(JobModel.id == one_job.scalar_subquery())
            .values(created_at=datetime.now(UTC) - timedelta(days=3))
        )
    start, end = window()
    admin = flow.admin()

    first = await admin.jobs(
        ADMIN, start=start, end=end, status=JobStatus.SUCCEEDED, job_type=None, limit=1, cursor=None
    )
    second = await admin.jobs(
        ADMIN,
        start=start,
        end=end,
        status=JobStatus.SUCCEEDED,
        job_type=None,
        limit=5,
        cursor=first.next_cursor,
    )
    other_type = await admin.jobs(
        ADMIN, start=start, end=end, status=None, job_type=JobType.MESSAGE, limit=5, cursor=None
    )

    mine = first.items + second.items
    assert len(first.items) == 1
    assert first.next_cursor is not None
    assert len({j.id for j in mine}) == len(mine)
    assert all(j.status is JobStatus.SUCCEEDED for j in mine)
    assert all(start <= j.created_at < end for j in mine)
    created = [j.created_at for j in mine]
    assert created == sorted(created, reverse=True)
    assert all(j.type is not JobType.MESSAGE for j in mine)
    assert all(j.type is JobType.MESSAGE for j in other_type.items)


async def test_recommendation_diagnostics_hold_no_personal_data(flow: Flow) -> None:
    flow.agent_state.scenario = "partial_disaster_down"
    user = await flow.user()
    rec_id = await recommend(flow, user, "ปลอดภัยไหม")

    record = await flow.admin().recommendation(ADMIN, rec_id)

    assert record.safety_gate_rules == ("R-02", "R-03")
    assert record.service_status["disaster"] == "unavailable"
    assert {i["category"] for i in record.data_freshness} >= {"WEATHER", "DISASTER"}
    assert record.job is not None
    assert record.job.status is JobStatus.SUCCEEDED
    assert [r.status.value for r in record.agent_runs] == ["success"]
    assert record.agent_runs[0].agent_version
    names = {f.name for f in fields(AdminRecommendationRecord)}
    assert not names & {"payload", "user_id", "origin_name", "destination_name", "question"}
    dumped = repr(record)
    assert "ปลอดภัยไหม" not in dumped
    assert str(user.id) not in dumped
    assert "13.7563" not in dumped


async def test_unknown_recommendation(flow: Flow) -> None:
    with pytest.raises(AppError):
        await flow.admin().recommendation(ADMIN, UUID(int=1))


async def test_admin_actions_are_audited_and_the_log_pages_by_id(flow: Flow) -> None:
    start, end = window()
    admin = flow.admin()
    for _ in range(3):
        await admin.jobs(
            ADMIN, start=start, end=end, status=None, job_type=None, limit=1, cursor=None
        )
    where = AuditFilter(action="admin.jobs_list", actor_type="admin", result="success")

    first = await admin.audit_logs(ADMIN, start=start, end=end, where=where, limit=2, cursor=None)
    second = await admin.audit_logs(
        ADMIN, start=start, end=end, where=where, limit=2, cursor=first.next_cursor
    )

    rows = first.items + second.items
    assert len(first.items) == 2
    assert len(rows) == len({r.id for r in rows}) >= 3
    assert all(r.action == "admin.jobs_list" and r.actor_ref == "admin-1" for r in rows)
    assert rows[0].metadata["count"] <= 1
    assert "from" in rows[0].metadata
    listed = await admin.audit_logs(
        ADMIN,
        start=start,
        end=end,
        where=AuditFilter(action="admin.audit_logs_list"),
        limit=10,
        cursor=None,
    )
    assert len(listed.items) >= 2  # reading the log is itself audited


async def test_training_export_holds_anonymized_rows_and_reviewed_feedback(flow: Flow) -> None:
    consenting, other = await flow.user(), await flow.user()
    await with_analytics(flow, consenting)
    reported = await recommend(flow, consenting, "question a")
    plain = await recommend(flow, consenting, "question b")
    await recommend(flow, other, "question c")  # no analytics consent: no prediction record
    feedback = flow.feedback()
    unsafe = await feedback.submit(
        consenting,
        reported,
        FeedbackInput(rating=1, report_type=ReportType.UNSAFE_ADVICE, comment="my flat at 12 Rd"),
        correlation_id="c",
        ip_hash=None,
    )
    await feedback.review(
        "reviewer-1",
        unsafe.id,
        decision=ReviewDecision.APPROVED,
        note=None,
        correlation_id="c",
        ip_hash=None,
    )
    await feedback.submit(
        consenting,
        plain,
        FeedbackInput(rating=5, outcome=FeedbackOutcome.FOLLOWED),
        correlation_id="c",
        ip_hash=None,
    )
    start, end = window()
    training = flow.training()

    requested = await training.request(ADMIN, start=start, end=end)
    assert [export_id for export_id, _ in flow.queue.training] == [requested.id]
    assert await training.build(requested.id) is True
    assert await training.build(requested.id) is False

    view = await training.get(ADMIN, requested.id)
    assert view.record.status is ExportStatus.READY
    assert view.record.row_count is not None
    assert view.record.row_count >= 2
    assert view.download_url == (
        f"https://storage.example/training/{requested.id}.jsonl.gz?expires=900"
    )
    data, content_type = flow.store.objects[f"training/{requested.id}.jsonl.gz"]
    assert content_type == "application/gzip"
    lines = [json.loads(line) for line in gzip.decompress(data).decode().splitlines()]
    assert len(lines) == view.record.row_count
    async with flow.repo.sessions() as session:
        ids = {
            str(row.id): row.recommendation_id
            for row in await session.scalars(
                select(PredictionRecordModel).where(
                    PredictionRecordModel.recommendation_id.in_([reported, plain])
                )
            )
        }
    mine = {ids[line["prediction_id"]]: line for line in lines if line["prediction_id"] in ids}
    assert set(mine) == {reported, plain}
    assert mine[reported]["feedback"] == [
        {"rating": 1, "helpful": None, "outcome": "UNKNOWN", "report_type": "UNSAFE_ADVICE"}
    ]
    assert mine[plain]["feedback"] == []  # not reviewed, so not training data
    text = gzip.decompress(data).decode()
    for secret in (str(reported), str(plain), str(consenting.id), consenting.pseudonymous_id):
        assert secret not in text
    assert "12 Rd" not in text
    assert "13.7563" not in text


async def test_training_export_file_expires_and_stuck_exports_fail(flow: Flow) -> None:
    start, end = window()
    training = flow.training()
    done = await training.request(ADMIN, start=start, end=end)
    stuck = await training.request(ADMIN, start=start, end=end)
    assert await training.build(done.id)
    async with flow.repo.sessions() as session, session.begin():
        await session.execute(
            update(TrainingExportModel)
            .where(TrainingExportModel.id == done.id)
            .values(expires_at=datetime.now(UTC) - HOUR)
        )
        await session.execute(
            update(TrainingExportModel)
            .where(TrainingExportModel.id == stuck.id)
            .values(created_at=datetime.now(UTC) - timedelta(hours=2))
        )

    purged = await flow.purge().run()
    reaped = await flow.reaper().run()

    assert purged.exports_expired >= 1
    assert f"training/{done.id}.jsonl.gz" not in flow.store.objects
    expired = await training.get(ADMIN, done.id)
    assert (expired.record.status, expired.download_url) == (ExportStatus.EXPIRED, None)
    assert reaped.exports_failed >= 1
    assert (await training.get(ADMIN, stuck.id)).record.status is ExportStatus.FAILED
