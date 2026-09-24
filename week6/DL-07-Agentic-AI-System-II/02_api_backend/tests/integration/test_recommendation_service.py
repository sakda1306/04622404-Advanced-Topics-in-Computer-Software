"""API use case: validation, sync/async decision, cache and failure handling."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from prometheus_client import REGISTRY

from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.domain.enums import JobStatus, RecommendationStatus, RequestMode
from app.domain.errors import InvalidInput
from app.domain.normalization import GeoPoint
from app.services.recommendation_service import Accepted, CreateRecommendation, Finished
from mock_agent.main import SCENARIOS
from tests.integration.flow import Flow, travel_input, tune

pytestmark = pytest.mark.integration

TOKYO = GeoPoint(35.6895, 139.6917, name="Tokyo")


def departure() -> datetime:
    # Start of a 15-minute bucket two days ahead, so repeated requests share a cache key.
    start = datetime.now(UTC) + timedelta(days=2)
    return start.replace(minute=start.minute - start.minute % 15, second=0, microsecond=0)


def command(mode: RequestMode = RequestMode.AUTO, **changes: Any) -> CreateRecommendation:
    conversation_id = changes.pop("conversation_id", None)
    changes.setdefault("departure_time", departure())
    return CreateRecommendation(
        input=travel_input(**changes),
        mode=mode,
        conversation_id=conversation_id,
        trip_id=None,
        correlation_id="corr-svc",
    )


@pytest.fixture
def slow_scenario(monkeypatch: pytest.MonkeyPatch) -> str:
    scenario = copy.deepcopy(SCENARIOS["slow_20s"])
    scenario["delay_seconds"] = 1
    monkeypatch.setitem(SCENARIOS, "slow_1s", scenario)
    return "slow_1s"


async def test_auto_mode_returns_the_finished_result(flow: Flow) -> None:
    user = await flow.user()

    outcome = await flow.recommendations().create(user, command())

    assert isinstance(outcome, Finished)
    assert outcome.record.status is RecommendationStatus.COMPLETED
    assert outcome.record.payload is not None
    assert outcome.record.payload["recommendation"]["type"] == "TRAVEL_NORMALLY"
    assert flow.queue.enqueued[0][1] == "corr-svc"


async def test_async_mode_accepts_and_finishes_later(flow: Flow) -> None:
    user = await flow.user()
    service = flow.recommendations()

    outcome = await service.create(user, command(RequestMode.ASYNC))

    assert isinstance(outcome, Accepted)
    await flow.queue.drain()
    record = await service.get(user, outcome.recommendation_id)
    assert record.status is RecommendationStatus.COMPLETED
    assert record.conversation_id == outcome.conversation_id
    job = await flow.repo.get_job(user.id, outcome.job_id)
    assert job is not None
    assert job.status is JobStatus.SUCCEEDED


async def test_slow_agent_turns_auto_into_accepted(flow: Flow, slow_scenario: str) -> None:
    flow.agent_state.scenario = slow_scenario
    user = await flow.user()
    settings = tune(flow.settings, agent={"sync_agent_timeout_seconds": 0.2})

    outcome = await flow.recommendations(settings).create(user, command())

    assert isinstance(outcome, Accepted)
    await flow.queue.drain()


async def test_slow_agent_in_sync_mode_is_a_timeout(flow: Flow, slow_scenario: str) -> None:
    flow.agent_state.scenario = slow_scenario
    user = await flow.user()
    settings = tune(flow.settings, agent={"sync_agent_timeout_seconds": 0.2})

    with pytest.raises(AppError) as info:
        await flow.recommendations(settings).create(user, command(RequestMode.SYNC))

    assert info.value.code is ErrorCode.AGENT_TIMEOUT
    await flow.queue.drain()


async def test_failed_job_is_reported_as_its_error(flow: Flow) -> None:
    flow.agent_state.scenario = "bad_schema"
    user = await flow.user()

    with pytest.raises(AppError) as info:
        await flow.recommendations().create(user, command())

    assert info.value.code is ErrorCode.AGENT_BAD_RESPONSE


async def test_unavailable_agent_error_has_retry_after(flow: Flow) -> None:
    flow.agent_state.scenario = "unavailable_503"
    user = await flow.user()
    settings = tune(flow.settings, agent={"agent_max_retries": 0})

    with pytest.raises(AppError) as info:
        await flow.recommendations(settings).create(user, command())

    assert info.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert info.value.retry_after == 5


async def test_location_outside_the_service_area(flow: Flow) -> None:
    user = await flow.user()

    with pytest.raises(AppError) as info:
        await flow.recommendations().create(
            user, command(origin=TOKYO, waypoints=(GeoPoint(34.69, 135.50),))
        )

    assert info.value.code is ErrorCode.UNSUPPORTED_REGION
    assert [e.field for e in info.value.errors or []] == ["origin", "waypoints.0"]
    assert flow.queue.enqueued == []


async def test_invalid_input_is_reported_before_any_work(flow: Flow) -> None:
    user = await flow.user()

    with pytest.raises(InvalidInput) as info:
        await flow.recommendations().create(user, command(timezone="Mars/Olympus"))

    assert [i.field for i in info.value.issues] == ["timezone"]
    assert flow.queue.enqueued == []


async def test_foreign_conversation_is_not_found(flow: Flow) -> None:
    owner, intruder = await flow.user(), await flow.user()
    service = flow.recommendations()
    first = await service.create(owner, command(RequestMode.ASYNC))
    assert isinstance(first, Accepted)
    await flow.queue.drain()

    with pytest.raises(AppError) as info:
        await service.create(intruder, command(conversation_id=first.conversation_id))

    assert info.value.code is ErrorCode.NOT_FOUND


async def test_foreign_trip_is_not_found(flow: Flow) -> None:
    user = await flow.user()
    base = command()
    unknown_trip = CreateRecommendation(
        input=base.input,
        mode=base.mode,
        conversation_id=None,
        trip_id=new_id(),
        correlation_id="corr-svc",
    )

    with pytest.raises(AppError) as info:
        await flow.recommendations().create(user, unknown_trip)

    assert info.value.code is ErrorCode.NOT_FOUND


async def test_too_many_active_jobs(flow: Flow) -> None:
    user = await flow.user()
    settings = tune(flow.settings, limits={"max_active_jobs_per_user": 2})
    for name in ("a", "b"):
        await flow.slots.acquire(flow.keys.active_jobs(user.id), name, limit=2, ttl_seconds=60)

    with pytest.raises(AppError) as info:
        await flow.recommendations(settings).create(user, command())

    assert info.value.code is ErrorCode.TOO_MANY_ACTIVE_JOBS
    assert info.value.retry_after == 5
    assert flow.queue.enqueued == []


async def test_queue_failure_marks_the_job_failed(flow: Flow) -> None:
    user = await flow.user()
    flow.queue.fail = True

    with pytest.raises(AppError) as info:
        await flow.recommendations().create(user, command())

    assert info.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert await flow.redis.zcard(flow.keys.active_jobs(user.id)) == 0
    job_id, _ = flow.queue.failed[0]
    job = await flow.repo.get_job(user.id, job_id)
    assert job is not None
    assert (job.status, job.error_code) == (JobStatus.FAILED, "DEPENDENCY_UNAVAILABLE")
    events = await flow.jobs.read(job_id, after="0-0", block_ms=None)
    assert events[-1].event == "failed"


async def test_cached_result_is_reused_with_a_new_id(flow: Flow) -> None:
    user = await flow.user()
    service = flow.recommendations()
    misses = REGISTRY.get_sample_value("cache_misses_total") or 0.0
    first = await service.create(user, command())
    assert isinstance(first, Finished)
    runs = len(flow.agent_state.runs)
    hits = REGISTRY.get_sample_value("cache_hits_total") or 0.0

    second = await service.create(user, command())

    assert isinstance(second, Finished)
    assert len(flow.agent_state.runs) == runs
    assert REGISTRY.get_sample_value("cache_misses_total") == misses + 1
    assert REGISTRY.get_sample_value("cache_hits_total") == hits + 1
    assert second.record.id != first.record.id
    assert second.record.status is RecommendationStatus.COMPLETED
    assert first.record.payload is not None
    assert second.record.payload is not None
    assert second.record.payload["recommendation"] == first.record.payload["recommendation"]


async def test_cache_is_not_used_for_questions_or_async(flow: Flow) -> None:
    user = await flow.user()
    service = flow.recommendations()
    await service.create(user, command())
    runs = len(flow.agent_state.runs)

    await service.create(user, command(question="Is it safe?"))
    queued = await service.create(user, command(RequestMode.ASYNC))
    await flow.queue.drain()

    assert isinstance(queued, Accepted)
    assert len(flow.agent_state.runs) == runs + 2


async def test_stale_cache_entry_is_ignored(flow: Flow) -> None:
    user = await flow.user()
    service = flow.recommendations()
    first = await service.create(user, command())
    assert isinstance(first, Finished)
    for key in await flow.redis.keys("*reco:*"):
        entry = await flow.cache.get(key.decode().rsplit(":", 1)[1])
        assert entry is not None
        for item in entry["data_freshness"]["items"]:
            item["updated_at"] = "2020-01-01T00:00:00Z"
        await flow.cache.put(key.decode().rsplit(":", 1)[1], entry, ttl_seconds=60)
    runs = len(flow.agent_state.runs)

    await service.create(user, command())

    assert len(flow.agent_state.runs) == runs + 1


async def test_get_of_another_users_recommendation(flow: Flow) -> None:
    owner, intruder = await flow.user(), await flow.user()
    service = flow.recommendations()
    outcome = await service.create(owner, command())
    assert isinstance(outcome, Finished)

    with pytest.raises(AppError) as info:
        await service.get(intruder, outcome.record.id)

    assert info.value.code is ErrorCode.NOT_FOUND
