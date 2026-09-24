"""Cancelling jobs (E-05) through the real worker path, and prediction records."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import select

from app.core.errors import AppError, ErrorCode
from app.domain.enums import (
    AgentRunStatus,
    JobStatus,
    RecommendationStatus,
    RequestMode,
    RequestSource,
)
from app.domain.normalization import NormalizationLimits, normalize_travel_request
from app.infrastructure.db.models import (
    AgentRunModel,
    JobModel,
    PredictionRecordModel,
    RecommendationModel,
    UserModel,
)
from app.services.ports import NewRecommendation, UserRef
from tests.integration.flow import Flow, travel_input

pytestmark = pytest.mark.integration


def new(user: UserRef) -> NewRecommendation:
    now = datetime.now(UTC)
    return NewRecommendation(
        user_id=user.id,
        request=normalize_travel_request(travel_input(), now=now, limits=NormalizationLimits()),
        mode=RequestMode.ASYNC,
        source=RequestSource.RECOMMENDATION,
        conversation_id=None,
        trip_id=None,
        cache_key=None,
        correlation_id="corr-cancel",
        now=now,
        retention_days=30,
        conversation_days=30,
    )


async def wait_until_running(flow: Flow, job_id: UUID) -> None:
    for _ in range(200):
        async with flow.repo.sessions() as session:
            status = await session.scalar(select(JobModel.status).where(JobModel.id == job_id))
        if status == JobStatus.RUNNING.value and flow.agent_state.runs:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("the job never started")


async def test_cancel_a_running_job(flow: Flow) -> None:
    flow.agent_state.scenario = "slow_20s"
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user))
    worker = asyncio.create_task(flow.worker().run(job_id))
    await wait_until_running(flow, job_id)
    counted = REGISTRY.get_sample_value("jobs_total", {"status": "cancelled"}) or 0.0

    cancelled = await flow.jobs_service().cancel(user.id, job_id)
    status = await asyncio.wait_for(worker, timeout=5)

    assert cancelled.status is JobStatus.CANCELLED
    assert status is JobStatus.CANCELLED
    # Counted once, by the API; the worker only records its stopped Agent run.
    assert REGISTRY.get_sample_value("jobs_total", {"status": "cancelled"}) == counted + 1
    run_id = flow.agent_state.runs[-1]["run_id"]
    assert run_id in flow.agent_state.cancelled
    async with flow.repo.sessions() as session:
        rec = await session.get(RecommendationModel, rec_id)
        runs = (
            await session.scalars(select(AgentRunModel).where(AgentRunModel.job_id == job_id))
        ).all()
    assert rec is not None
    assert rec.status == RecommendationStatus.CANCELLED.value
    assert [r.status for r in runs] == [AgentRunStatus.CANCELLED.value]
    events = await flow.jobs.read(job_id, after="0-0", block_ms=None)
    assert [e.event for e in events if e.terminal] == ["cancelled"]
    snapshot = await flow.jobs.get(job_id)
    assert snapshot is not None
    assert snapshot.status is JobStatus.CANCELLED
    assert await flow.redis.zscore(flow.keys.active_jobs(user.id), str(job_id)) is None


async def test_cancelled_queued_job_is_skipped_by_the_worker(flow: Flow) -> None:
    user = await flow.user()
    job_id, _ = await flow.queued_job(new(user))
    await flow.jobs_service().cancel(user.id, job_id)

    assert await flow.worker().run(job_id) is None
    assert flow.agent_state.runs == []


async def test_cancel_rules(flow: Flow) -> None:
    user, other = await flow.user(), await flow.user()
    job_id, _ = await flow.queued_job(new(user))
    jobs = flow.jobs_service()

    with pytest.raises(AppError) as missing:
        await jobs.cancel(other.id, job_id)
    await jobs.cancel(user.id, job_id)
    with pytest.raises(AppError) as again:
        await jobs.cancel(user.id, job_id)

    assert missing.value.code is ErrorCode.NOT_FOUND
    assert again.value.code is ErrorCode.JOB_NOT_CANCELLABLE


async def test_successful_job_writes_a_prediction_with_consent(flow: Flow) -> None:
    user = await flow.user()
    async with flow.repo.sessions() as session, session.begin():
        row = await session.get(UserModel, user.id)
        assert row is not None
        row.consent_analytics = True
    job_id, rec_id = await flow.queued_job(new(user))

    assert await flow.worker().run(job_id) is JobStatus.SUCCEEDED

    async with flow.repo.sessions() as session:
        stored = await session.scalar(
            select(PredictionRecordModel).where(PredictionRecordModel.recommendation_id == rec_id)
        )
    assert stored is not None
    assert len(stored.origin_geohash) == flow.settings.privacy.prediction_geohash_precision
    assert stored.region_code == "TH"
    assert stored.travel_modes == ["TRAIN"]
    assert "13.75" not in repr(stored.__dict__)


async def test_no_prediction_without_consent(flow: Flow) -> None:
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user))

    await flow.worker().run(job_id)

    async with flow.repo.sessions() as session:
        stored = await session.scalar(
            select(PredictionRecordModel.id).where(
                PredictionRecordModel.recommendation_id == rec_id
            )
        )
    assert stored is None
