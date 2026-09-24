"""Redis stores of the recommendation flow, against fakeredis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.ids import new_id
from app.domain.enums import JobStage, JobStatus, JobType
from app.infrastructure.redis.cache import RedisRecommendationCache
from app.infrastructure.redis.job_state import JobSnapshot, RedisJobStateStore
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.slots import RedisSlotLimiter
from app.infrastructure.redis.tickets import RedisTicketStore

KEYS = RedisKeys("test")
T0 = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)


def snapshot(**changes: object) -> JobSnapshot:
    values: dict[str, object] = {
        "job_id": new_id(),
        "user_id": new_id(),
        "type": JobType.RECOMMENDATION,
        "status": JobStatus.QUEUED,
        "stage": JobStage.QUEUED,
        "progress": 0,
        "recommendation_id": new_id(),
        "error_code": None,
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(changes)
    return JobSnapshot(**values)  # type: ignore[arg-type]


@pytest.fixture
def jobs(redis: FakeAsyncRedis) -> RedisJobStateStore:
    return RedisJobStateStore(redis, KEYS, ttl_seconds=3600, max_events=10)


# ------------------------------------------------------------------ job state


async def test_snapshot_round_trip(jobs: RedisJobStateStore) -> None:
    job = snapshot()

    await jobs.create(job)

    assert await jobs.get(job.job_id) == job


async def test_unknown_job_is_none(jobs: RedisJobStateStore) -> None:
    assert await jobs.get(new_id()) is None


async def test_update_changes_only_given_fields(jobs: RedisJobStateStore) -> None:
    job = snapshot()
    await jobs.create(job)
    later = T0 + timedelta(seconds=5)

    await jobs.update(job.job_id, updated_at=later, stage=JobStage.ASSESSING_RISK, progress=60)
    await jobs.update(
        job.job_id, updated_at=later, status=JobStatus.FAILED, error_code="AGENT_TIMEOUT"
    )

    stored = await jobs.get(job.job_id)
    assert stored is not None
    assert (stored.status, stored.stage, stored.progress) == (
        JobStatus.FAILED,
        JobStage.ASSESSING_RISK,
        60,
    )
    assert stored.error_code == "AGENT_TIMEOUT"
    assert stored.updated_at == later
    assert stored.created_at == T0


async def test_update_of_expired_job_does_not_create_a_partial_hash(
    jobs: RedisJobStateStore, redis: FakeAsyncRedis
) -> None:
    job_id = new_id()

    await jobs.update(job_id, updated_at=T0, progress=10)

    assert await redis.exists(KEYS.job(job_id)) == 0


async def test_events_are_read_in_order_and_resumable(jobs: RedisJobStateStore) -> None:
    job_id = new_id()
    first = await jobs.publish(job_id, "progress", {"stage": "queued"})
    await jobs.publish(job_id, "progress", {"stage": "fetching_data"})
    await jobs.publish(job_id, "completed", {"status": "completed"})

    everything = await jobs.read(job_id, after="0-0", block_ms=None)
    later = await jobs.read(job_id, after=first, block_ms=None)

    assert [e.event for e in everything] == ["progress", "progress", "completed"]
    assert everything[0].id == first
    assert everything[1].data == {"stage": "fetching_data"}
    assert [e.data for e in later] == [{"stage": "fetching_data"}, {"status": "completed"}]
    assert [e.terminal for e in everything] == [False, False, True]


async def test_empty_stream_read_returns_after_block(jobs: RedisJobStateStore) -> None:
    assert await jobs.read(new_id(), after="0-0", block_ms=50) == []


async def test_keys_expire_and_stream_is_trimmed(
    jobs: RedisJobStateStore, redis: FakeAsyncRedis
) -> None:
    job = snapshot()
    await jobs.create(job)
    for number in range(200):
        await jobs.publish(job.job_id, "progress", {"n": number})

    assert 0 < await redis.ttl(KEYS.job(job.job_id)) <= 3600
    assert 0 < await redis.ttl(KEYS.job_events(job.job_id)) <= 3600
    assert await redis.xlen(KEYS.job_events(job.job_id)) < 200


# ------------------------------------------------------------------ slots


async def test_slots_limit_distinct_members(redis: FakeAsyncRedis) -> None:
    slots = RedisSlotLimiter(redis)

    first = await slots.acquire("k", "a", limit=2, ttl_seconds=60)
    second = await slots.acquire("k", "b", limit=2, ttl_seconds=60)
    third = await slots.acquire("k", "c", limit=2, ttl_seconds=60)
    again = await slots.acquire("k", "a", limit=2, ttl_seconds=60)

    assert (first, second, third, again) == (True, True, False, True)
    await slots.release("k", "a")
    assert await slots.acquire("k", "c", limit=2, ttl_seconds=60)
    assert 0 < await redis.pttl("k") <= 60_000


async def test_refresh_keeps_a_slot(redis: FakeAsyncRedis) -> None:
    slots = RedisSlotLimiter(redis)
    await slots.acquire("k", "a", limit=1, ttl_seconds=60)

    await slots.refresh("k", "a", ttl_seconds=120)

    assert await redis.zscore("k", "a") is not None
    assert 60_000 < await redis.pttl("k") <= 120_000


# ------------------------------------------------------------------ tickets


async def test_ticket_is_single_use(redis: FakeAsyncRedis) -> None:
    tickets = RedisTicketStore(redis, KEYS)
    user_id, job_id = new_id(), new_id()

    ticket = await tickets.issue(user_id, job_id, ttl_seconds=60)

    assert len(ticket) >= 32
    assert all(ticket not in key.decode() for key in await redis.keys("*"))
    assert 0 < await redis.ttl(KEYS.stream_ticket(ticket)) <= 60
    assert await tickets.redeem(ticket) == (user_id, job_id)
    assert await tickets.redeem(ticket) is None
    assert await tickets.redeem("unknown-ticket") is None


# ------------------------------------------------------------------ cache


async def test_cache_round_trip(redis: FakeAsyncRedis) -> None:
    cache = RedisRecommendationCache(redis, KEYS)

    await cache.put("abc", {"status": "completed", "summary": "ไปได้"}, ttl_seconds=120)

    assert await cache.get("abc") == {"status": "completed", "summary": "ไปได้"}
    assert 0 < await redis.ttl(KEYS.recommendation_cache("abc")) <= 120
    assert await cache.get("missing") is None


async def test_cache_skips_zero_ttl(redis: FakeAsyncRedis) -> None:
    cache = RedisRecommendationCache(redis, KEYS)

    await cache.put("abc", {"a": 1}, ttl_seconds=0)

    assert await cache.get("abc") is None


async def test_broken_cache_entry_is_a_miss(redis: FakeAsyncRedis) -> None:
    await redis.set(KEYS.recommendation_cache("abc"), b"{not json")

    assert await RedisRecommendationCache(redis, KEYS).get("abc") is None


class BrokenRedis:
    async def get(self, *args: object, **kwargs: object) -> None:
        raise RedisConnectionError("down")

    async def set(self, *args: object, **kwargs: object) -> None:
        raise RedisConnectionError("down")


async def test_cache_outage_is_not_an_error() -> None:
    cache = RedisRecommendationCache(BrokenRedis(), KEYS)  # type: ignore[arg-type]

    await cache.put("abc", {"a": 1}, ttl_seconds=60)

    assert await cache.get("abc") is None


@pytest.mark.parametrize("final", [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED])
async def test_terminal_status_is_never_left(jobs: RedisJobStateStore, final: JobStatus) -> None:
    job = snapshot()
    await jobs.create(job)
    await jobs.update(job.job_id, updated_at=T0, status=final)

    # A late progress update from a worker must not bring the job back (D-73).
    await jobs.update(
        job.job_id, updated_at=T0, status=JobStatus.RUNNING, stage=JobStage.ASSESSING_RISK
    )

    stored = await jobs.get(job.job_id)
    assert stored is not None
    assert stored.status is final
    assert stored.stage is JobStage.QUEUED
