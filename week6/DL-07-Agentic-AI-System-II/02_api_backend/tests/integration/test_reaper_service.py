"""The reaper closes stuck jobs and retries pending account deletions (D-74, D-78)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import JobStatus, RequestMode, RequestSource
from app.domain.normalization import NormalizationLimits, normalize_travel_request
from app.infrastructure.db.models import JobModel
from app.infrastructure.db.repositories.users import SqlUserRepository
from app.services.ports import NewRecommendation, UserRef
from tests.integration.flow import Flow, travel_input

pytestmark = pytest.mark.integration


def new(user: UserRef, *, age: timedelta = timedelta(0)) -> NewRecommendation:
    now = datetime.now(UTC)
    request = normalize_travel_request(travel_input(), now=now, limits=NormalizationLimits())
    return NewRecommendation(
        user_id=user.id,
        request=request,
        mode=RequestMode.ASYNC,
        source=RequestSource.RECOMMENDATION,
        conversation_id=None,
        trip_id=None,
        cache_key=None,
        correlation_id="corr-reaper",
        now=now - age,
        retention_days=30,
        conversation_days=30,
    )


async def test_stuck_job_is_failed_and_announced(flow: Flow) -> None:
    user = await flow.user()
    stuck_id, _ = await flow.queued_job(new(user, age=timedelta(minutes=5)))
    fresh_id, _ = await flow.queued_job(new(user))

    result = await flow.reaper().run()

    assert result.reaped >= 1
    async with flow.repo.sessions() as session:
        stuck = await session.get(JobModel, stuck_id)
        fresh = await session.get(JobModel, fresh_id)
    assert stuck is not None
    assert stuck.status == JobStatus.FAILED.value
    assert stuck.error_code == "AGENT_TIMEOUT"
    assert fresh is not None
    assert fresh.status == JobStatus.QUEUED.value
    events = await flow.jobs.read(stuck_id, after="0-0", block_ms=None)
    final = [e for e in events if e.terminal]
    assert [e.event for e in final] == ["failed"]
    assert final[0].data["error"]["code"] == "AGENT_TIMEOUT"
    snapshot = await flow.jobs.get(stuck_id)
    assert snapshot is not None
    assert snapshot.status is JobStatus.FAILED
    active = flow.keys.active_jobs(user.id)
    assert await flow.redis.zscore(active, str(stuck_id)) is None
    assert await flow.redis.zscore(active, str(fresh_id)) is not None


async def test_worker_skips_a_reaped_job(flow: Flow) -> None:
    user = await flow.user()
    job_id, _ = await flow.queued_job(new(user, age=timedelta(minutes=5)))
    await flow.reaper().run()

    assert await flow.worker().run(job_id) is None
    assert flow.agent_state.runs == []


async def test_pending_deletions_are_queued_again(flow: Flow) -> None:
    old, fresh = await flow.user(), await flow.user()
    users = SqlUserRepository(flow.repo.sessions)
    await users.request_deletion(old.id, now=datetime.now(UTC) - timedelta(minutes=30))
    await users.request_deletion(fresh.id, now=datetime.now(UTC))

    result = await flow.reaper().run()

    queued = {user_id for user_id, _ in flow.queue.deletions}
    assert old.id in queued
    assert fresh.id not in queued
    assert result.deletions_requeued >= 1
