"""Job status, SSE event stream and stream tickets."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fakeredis import FakeAsyncRedis

from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.domain.enums import JobStage, JobStatus, JobType, RecommendationStatus
from app.infrastructure.redis.job_state import JobEvent, JobSnapshot, RedisJobStateStore
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.slots import RedisSlotLimiter
from app.infrastructure.redis.tickets import RedisTicketStore
from app.services.job_service import JobService
from app.services.ports import JobRecord, RecommendationRecord

KEYS = RedisKeys("test")
T0 = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
OWNER = new_id()
INTRUDER = new_id()


@dataclass
class FakeRepository:
    jobs: dict[UUID, JobRecord] = field(default_factory=dict)
    recommendations: dict[UUID, RecommendationRecord] = field(default_factory=dict)

    async def get_job(self, user_id: UUID, job_id: UUID) -> JobRecord | None:
        job = self.jobs.get(job_id)
        return job if job is not None and job.user_id == user_id else None

    async def get_recommendation(
        self, user_id: UUID, recommendation_id: UUID
    ) -> RecommendationRecord | None:
        record = self.recommendations.get(recommendation_id)
        return record if record is not None and record.user_id == user_id else None


def job_record(status: JobStatus = JobStatus.SUCCEEDED, **changes: object) -> JobRecord:
    values: dict[str, object] = {
        "id": new_id(),
        "user_id": OWNER,
        "type": JobType.RECOMMENDATION,
        "status": status,
        "stage": JobStage.COMPLETED,
        "progress": 100,
        "recommendation_id": new_id(),
        "error_code": None,
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(changes)
    return JobRecord(**values)  # type: ignore[arg-type]


@pytest.fixture
def repo() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def jobs(redis: FakeAsyncRedis) -> RedisJobStateStore:
    return RedisJobStateStore(redis, KEYS, ttl_seconds=3600)


def build(
    settings: Settings, repo: FakeRepository, jobs: RedisJobStateStore, redis: FakeAsyncRedis
) -> JobService:
    fast = settings.model_copy(
        update={
            "limits": settings.limits.model_copy(
                update={"sse_heartbeat_seconds": 1, "max_streams_per_user": 2}
            ),
            "jobs": settings.jobs.model_copy(update={"sse_max_stream_seconds": 2}),
        }
    )
    return JobService(
        repository=repo,  # type: ignore[arg-type]
        job_state=jobs,
        slots=RedisSlotLimiter(redis),
        tickets=RedisTicketStore(redis, KEYS),
        keys=KEYS,
        settings=fast,
        clock=SystemClock(),
    )


@pytest.fixture
def service(
    settings: Settings, repo: FakeRepository, jobs: RedisJobStateStore, redis: FakeAsyncRedis
) -> JobService:
    return build(settings, repo, jobs, redis)


async def live_job(jobs: RedisJobStateStore, user_id: UUID = OWNER) -> UUID:
    job_id = new_id()
    await jobs.create(
        JobSnapshot(
            job_id,
            user_id,
            JobType.RECOMMENDATION,
            JobStatus.RUNNING,
            JobStage.ASSESSING_RISK,
            60,
            new_id(),
            None,
            T0,
            T0,
        )
    )
    return job_id


async def collect(
    service: JobService, job: JobRecord, last: str | None = None
) -> list[JobEvent | None]:
    return [event async for event in service.stream(OWNER, job, "conn-1", last_event_id=last)]


# ------------------------------------------------------------------ status


async def test_status_comes_from_redis_first(service: JobService, jobs: RedisJobStateStore) -> None:
    job_id = await live_job(jobs)

    job = await service.get(OWNER, job_id)

    assert (job.status, job.stage, job.progress) == (
        JobStatus.RUNNING,
        JobStage.ASSESSING_RISK,
        60,
    )


async def test_status_falls_back_to_the_database(service: JobService, repo: FakeRepository) -> None:
    record = job_record()
    repo.jobs[record.id] = record

    assert await service.get(OWNER, record.id) == record


async def test_other_users_job_is_not_found(
    service: JobService, jobs: RedisJobStateStore, repo: FakeRepository
) -> None:
    live = await live_job(jobs)
    stored = job_record()
    repo.jobs[stored.id] = stored

    for job_id in (live, stored.id, new_id()):
        with pytest.raises(AppError) as info:
            await service.get(INTRUDER, job_id)
        assert info.value.code is ErrorCode.NOT_FOUND


# ------------------------------------------------------------------ stream


async def test_stream_stops_after_the_final_event(
    service: JobService, jobs: RedisJobStateStore
) -> None:
    job_id = await live_job(jobs)
    await jobs.publish(job_id, "progress", {"stage": "queued"})
    await jobs.publish(job_id, "completed", {"status": "completed"})
    await jobs.publish(job_id, "progress", {"stage": "after-the-end"})
    job = await service.get(OWNER, job_id)

    events = await collect(service, job)

    assert [e.event for e in events if e is not None] == ["progress", "completed"]


async def test_stream_resumes_after_last_event_id(
    service: JobService, jobs: RedisJobStateStore
) -> None:
    job_id = await live_job(jobs)
    first = await jobs.publish(job_id, "progress", {"stage": "queued"})
    await jobs.publish(job_id, "failed", {"error": {"code": "AGENT_TIMEOUT"}})
    job = await service.get(OWNER, job_id)

    resumed = await collect(service, job, last=first)
    garbage = await collect(service, job, last="not-an-id")

    assert [e.event for e in resumed if e is not None] == ["failed"]
    assert [e.event for e in garbage if e is not None] == ["progress", "failed"]


async def test_idle_stream_sends_heartbeats_until_the_limit(
    service: JobService, jobs: RedisJobStateStore
) -> None:
    job_id = await live_job(jobs)
    await jobs.publish(job_id, "progress", {"stage": "queued"})
    job = await service.get(OWNER, job_id)

    events = await collect(service, job)

    assert events[0] is not None
    assert events[1:] == [None, None] or events[1:] == [None]


async def test_finished_job_without_events_gets_one_final_event(
    service: JobService, repo: FakeRepository
) -> None:
    stored = job_record()
    repo.jobs[stored.id] = stored
    assert stored.recommendation_id is not None
    repo.recommendations[stored.recommendation_id] = RecommendationRecord(
        stored.recommendation_id,
        OWNER,
        new_id(),
        None,
        RecommendationStatus.PARTIAL_RESULT,
        {},
        None,
        T0,
        None,
    )

    events = await collect(service, stored)

    assert len(events) == 1
    final = events[0]
    assert final is not None
    assert final.event == "completed"
    assert final.data == {
        "job_id": str(stored.id),
        "status": "partial_result",
        "result_url": f"/v1/travel/recommendations/{stored.recommendation_id}",
    }


async def test_failed_job_without_events(service: JobService, repo: FakeRepository) -> None:
    stored = job_record(JobStatus.FAILED, stage=JobStage.FAILED, error_code="AGENT_TIMEOUT")
    repo.jobs[stored.id] = stored

    events = await collect(service, stored)

    assert len(events) == 1
    assert events[0] is not None
    assert events[0].event == "failed"
    assert events[0].data["error"]["code"] == "AGENT_TIMEOUT"


async def test_open_streams_are_limited(
    service: JobService, jobs: RedisJobStateStore, redis: FakeAsyncRedis
) -> None:
    job_id = await live_job(jobs)
    first = await service.open_stream(OWNER, job_id)
    await service.open_stream(OWNER, job_id)

    with pytest.raises(AppError) as info:
        await service.open_stream(OWNER, job_id)

    assert info.value.code is ErrorCode.RATE_LIMITED
    await service.close_stream(OWNER, first[1])
    assert await service.open_stream(OWNER, job_id)
    assert await redis.zcard(KEYS.streams(OWNER)) == 2


async def test_stream_of_other_users_job_is_not_opened(
    service: JobService, jobs: RedisJobStateStore
) -> None:
    job_id = await live_job(jobs)

    with pytest.raises(AppError) as info:
        await service.open_stream(INTRUDER, job_id)

    assert info.value.code is ErrorCode.NOT_FOUND


# ------------------------------------------------------------------ tickets


async def test_ticket_is_bound_to_one_job_and_one_use(
    service: JobService, jobs: RedisJobStateStore
) -> None:
    job_id = await live_job(jobs)

    ticket, expires_in = await service.issue_ticket(OWNER, job_id)

    assert expires_in == 60
    assert await service.redeem_ticket(ticket, job_id) == OWNER
    with pytest.raises(AppError) as reused:
        await service.redeem_ticket(ticket, job_id)
    assert reused.value.code is ErrorCode.UNAUTHENTICATED


async def test_ticket_for_another_job_is_refused(
    service: JobService, jobs: RedisJobStateStore
) -> None:
    job_id = await live_job(jobs)
    ticket, _ = await service.issue_ticket(OWNER, job_id)

    with pytest.raises(AppError) as info:
        await service.redeem_ticket(ticket, new_id())

    assert info.value.code is ErrorCode.UNAUTHENTICATED


async def test_ticket_needs_ownership(service: JobService, jobs: RedisJobStateStore) -> None:
    job_id = await live_job(jobs)

    with pytest.raises(AppError) as info:
        await service.issue_ticket(INTRUDER, job_id)

    assert info.value.code is ErrorCode.NOT_FOUND


async def test_stream_stops_soon_after_the_client_leaves(
    service: JobService, jobs: RedisJobStateStore
) -> None:
    job_id = await live_job(jobs)
    await jobs.publish(job_id, "progress", {"stage": "queued"})
    job = await service.get(OWNER, job_id)
    checks = 0

    async def disconnected() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    started = time.monotonic()
    events = [
        event
        async for event in service.stream(
            OWNER, job, "conn-1", last_event_id=None, disconnected=disconnected
        )
    ]

    assert [e.event for e in events if e is not None] == ["progress"]
    assert None not in events
    assert time.monotonic() - started < 1.5
