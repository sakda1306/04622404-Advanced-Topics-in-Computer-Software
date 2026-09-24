"""Worker use case: Agent call -> Safety Gate -> persistence -> job events."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from prometheus_client import REGISTRY
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.enums import JobStage, JobStatus, RequestMode, RequestSource, ServiceState
from app.domain.normalization import NormalizationLimits, normalize_travel_request
from app.infrastructure.db.models import AgentRunModel, RecommendationModel
from app.infrastructure.redis.service_status import RedisServiceStatusStore
from app.services.ports import NewRecommendation, UserRef
from mock_agent.main import SCENARIOS
from tests.integration.flow import Flow, travel_input, tune

pytestmark = pytest.mark.integration


def new(user: UserRef, *, cache_key: str | None = None, **changes: Any) -> NewRecommendation:
    now = datetime.now(UTC)
    request = normalize_travel_request(
        travel_input(**changes), now=now, limits=NormalizationLimits()
    )
    return NewRecommendation(
        user_id=user.id,
        request=request,
        mode=RequestMode.ASYNC,
        source=RequestSource.RECOMMENDATION,
        conversation_id=None,
        trip_id=None,
        cache_key=cache_key,
        correlation_id="corr-test",
        now=now,
        retention_days=30,
        conversation_days=30,
    )


async def recommendation_row(
    factory: async_sessionmaker[AsyncSession], recommendation_id: UUID
) -> RecommendationModel:
    async with factory() as session:
        row = await session.get(RecommendationModel, recommendation_id)
    assert row is not None
    return row


async def agent_run_rows(
    factory: async_sessionmaker[AsyncSession], job_id: UUID
) -> list[AgentRunModel]:
    async with factory() as session:
        return list(
            await session.scalars(select(AgentRunModel).where(AgentRunModel.job_id == job_id))
        )


async def test_low_risk_job_succeeds(
    flow: Flow, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user, cache_key="k" * 64))

    status = await flow.worker().run(job_id)

    assert status is JobStatus.SUCCEEDED
    row = await recommendation_row(session_factory, rec_id)
    assert row.status == "completed"
    assert row.recommendation_type == "TRAVEL_NORMALLY"
    assert row.payload is not None
    assert row.payload["recommendation"]["type"] == "TRAVEL_NORMALLY"
    events = await flow.jobs.read(job_id, after="0-0", block_ms=None)
    assert events[0].event == "progress"
    assert events[0].data["stage"] == "fetching_data"
    assert events[-1].event == "completed"
    assert events[-1].data == {
        "job_id": str(job_id),
        "status": "completed",
        "result_url": f"/v1/travel/recommendations/{rec_id}",
    }
    snapshot = await flow.jobs.get(job_id)
    assert snapshot is not None
    assert (snapshot.status, snapshot.stage, snapshot.progress) == (
        JobStatus.SUCCEEDED,
        JobStage.COMPLETED,
        100,
    )
    assert await flow.redis.zcard(flow.keys.active_jobs(user.id)) == 0
    assert await flow.cache.get("k" * 64) == row.payload
    runs = await agent_run_rows(session_factory, job_id)
    assert [(r.status, r.attempt, r.tool_calls, r.http_status) for r in runs] == [
        ("success", 1, 6, 200)
    ]


async def test_progress_follows_the_agent_stream_in_the_request_language(flow: Flow) -> None:
    user = await flow.user()
    job_id, _ = await flow.queued_job(new(user, language="th"))

    await flow.worker().run(job_id)

    events = await flow.jobs.read(job_id, after="0-0", block_ms=None)
    progress = [(e.data["stage"], e.data["progress"]) for e in events if e.event == "progress"]
    # The worker's own "fetching_data" is not repeated when the Agent reports it too.
    assert progress == [
        ("fetching_data", 20),
        ("assessing_risk", 60),
        ("generating_advice", 90),
    ]
    assessing = next(e for e in events if e.data.get("stage") == "assessing_risk")
    assert assessing.data["message"] == "กำลังประเมินความเสี่ยง"
    assert assessing.data["job_id"] == str(job_id)
    assert assessing.data["at"].endswith("Z")


async def test_missing_disaster_data_is_partial_and_not_cached(
    flow: Flow, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    flow.agent_state.scenario = "partial_disaster_down"
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user, cache_key="p" * 64))

    assert await flow.worker().run(job_id) is JobStatus.SUCCEEDED

    row = await recommendation_row(session_factory, rec_id)
    assert row.status == "partial_result"
    assert row.recommendation_type is None
    assert row.safety_gate_rules == ["R-02", "R-03"]
    assert await flow.cache.get("p" * 64) is None
    events = await flow.jobs.read(job_id, after="0-0", block_ms=None)
    assert events[-1].data["status"] == "partial_result"


async def test_high_risk_keeps_emergency_instructions(
    flow: Flow, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    flow.agent_state.scenario = "high_risk"
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user, cache_key="h" * 64))

    await flow.worker().run(job_id)

    row = await recommendation_row(session_factory, rec_id)
    assert row.risk_level == "HIGH"
    assert row.payload is not None
    assert row.payload["emergency_instructions"]["contacts"]
    assert await flow.cache.get("h" * 64) is None


async def test_high_risk_without_instructions_uses_regional_defaults(
    flow: Flow,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = copy.deepcopy(SCENARIOS["high_risk"])
    scenario["response"]["emergency_instructions"] = None
    monkeypatch.setitem(SCENARIOS, "high_no_steps", scenario)
    flow.agent_state.scenario = "high_no_steps"
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user, language="th"))

    await flow.worker().run(job_id)

    row = await recommendation_row(session_factory, rec_id)
    assert row.status == "completed"
    assert "R-01" in row.safety_gate_rules
    assert row.payload is not None
    assert row.payload["emergency_instructions"]["contacts"][0]["phone"] == "191"


async def test_bad_agent_response_fails_the_job(
    flow: Flow, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    flow.agent_state.scenario = "bad_schema"
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user))

    assert await flow.worker().run(job_id) is JobStatus.FAILED

    row = await recommendation_row(session_factory, rec_id)
    assert (row.status, row.error_code) == ("failed", "AGENT_BAD_RESPONSE")
    events = await flow.jobs.read(job_id, after="0-0", block_ms=None)
    assert events[-1].event == "failed"
    assert events[-1].data["error"]["code"] == "AGENT_BAD_RESPONSE"
    assert events[-1].data["error"]["message"]
    snapshot = await flow.jobs.get(job_id)
    assert snapshot is not None
    assert (snapshot.status, snapshot.stage, snapshot.error_code) == (
        JobStatus.FAILED,
        JobStage.FAILED,
        "AGENT_BAD_RESPONSE",
    )
    assert await flow.redis.zcard(flow.keys.active_jobs(user.id)) == 0
    runs = await agent_run_rows(session_factory, job_id)
    assert [r.status for r in runs] == ["bad_response"]


async def test_unavailable_agent_fails_with_503_code(
    flow: Flow, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    flow.agent_state.scenario = "unavailable_503"
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user))
    settings = tune(flow.settings, agent={"agent_max_retries": 0})

    await flow.worker(settings).run(job_id)

    row = await recommendation_row(session_factory, rec_id)
    assert row.error_code == "DEPENDENCY_UNAVAILABLE"
    runs = await agent_run_rows(session_factory, job_id)
    assert [(r.status, r.http_status) for r in runs] == [("error", 503)]


async def test_contradicting_result_is_rejected_for_safety_review(
    flow: Flow,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = copy.deepcopy(SCENARIOS["high_risk"])
    scenario["response"]["recommendation"]["type"] = "TRAVEL_NORMALLY"
    monkeypatch.setitem(SCENARIOS, "contradiction", scenario)
    flow.agent_state.scenario = "contradiction"
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user))
    rejected = sample("safety_gate_rejections_total", rule="R-04")

    await flow.worker().run(job_id)

    assert sample("safety_gate_rejections_total", rule="R-04") == rejected + 1
    row = await recommendation_row(session_factory, rec_id)
    assert (row.status, row.error_code) == ("failed", "AGENT_BAD_RESPONSE")
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    review = [line for line in lines if line["event"] == "safety_review_required"]
    assert review
    assert review[0]["rule"] == "R-04"
    assert review[0]["job_id"] == str(job_id)
    runs = await agent_run_rows(session_factory, job_id)
    assert [(r.status, r.error_code) for r in runs] == [("bad_response", "R-04")]


async def test_finished_job_is_not_run_again(flow: Flow) -> None:
    user = await flow.user()
    job_id, _ = await flow.queued_job(new(user))
    worker = flow.worker()
    await worker.run(job_id)
    calls = len(flow.agent_state.runs)

    assert await worker.run(job_id) is None
    assert len(flow.agent_state.runs) == calls


async def test_agent_receives_context_but_no_identity(flow: Flow) -> None:
    user = await flow.user()
    first = new(user, question="Is the north flooded?")
    first_job, first_rec = await flow.queued_job(first)
    await flow.worker().run(first_job)
    earlier = await flow.repo.get_recommendation(user.id, first_rec)
    assert earlier is not None
    follow_up = replace(
        new(user, question="And tomorrow?"), conversation_id=earlier.conversation_id
    )
    second_job, _ = await flow.queued_job(follow_up)

    await flow.worker().run(second_job)

    body = flow.agent_state.runs[-1]["body"]
    assert body["intent_hint"] == "FOLLOW_UP"
    assert body["request"]["question"] == "And tomorrow?"
    assert [m["content"] for m in body["context"]["messages"]] == [
        "Is the north flooded?",
        "Conditions are safe for your trip.",
    ]
    assert body["context"]["previous_recommendation_id"] == str(first_rec)
    assert body["user_profile"]["pseudonymous_id"] == user.pseudonymous_id
    text = json.dumps(body)
    assert "sub-" not in text
    assert str(user.id) not in text
    assert body["limits"]["max_tool_calls"] == flow.settings.agent.agent_max_tool_calls
    assert flow.agent_state.runs[-1]["headers"]["x-deadline"].endswith("Z")


class CrashingAgent:
    async def run(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("bug")


async def test_unexpected_error_still_ends_the_job(
    flow: Flow, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user))
    worker = flow.worker()
    worker._agent = CrashingAgent()  # type: ignore[assignment]

    assert await worker.run(job_id) is JobStatus.FAILED

    row = await recommendation_row(session_factory, rec_id)
    assert (row.status, row.error_code) == ("failed", "INTERNAL_ERROR")
    events = await flow.jobs.read(job_id, after="0-0", block_ms=None)
    assert events[-1].event == "failed"
    assert await flow.redis.zcard(flow.keys.active_jobs(user.id)) == 0


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def test_reported_service_states_feed_the_status_page(flow: Flow) -> None:
    flow.agent_state.scenario = "partial_disaster_down"
    user = await flow.user()
    job_id, _ = await flow.queued_job(new(user))

    await flow.worker().run(job_id)

    reports = await RedisServiceStatusStore(flow.redis, flow.keys).recent()
    assert reports["disaster"].state is ServiceState.UNAVAILABLE
    assert reports["weather"].state is ServiceState.OK
    assert await flow.redis.ttl(flow.keys.service_reports()) > 0


async def test_metrics_count_outcomes_and_safety_rules(
    flow: Flow, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    flow.agent_state.scenario = "partial_disaster_down"
    succeeded = sample("jobs_total", status="succeeded")
    r02 = sample("safety_gate_overrides_total", rule="R-02")
    r03 = sample("safety_gate_overrides_total", rule="R-03")
    calls = sample("agent_request_duration_seconds_count", outcome="success")
    user = await flow.user()
    job_id, rec_id = await flow.queued_job(new(user))
    partial = {"status": "partial_result", "recommendation_type": "none"}

    stored_before = {
        level: sample("recommendations_total", risk_level=level, **partial)
        for level in ("LOW", "MEDIUM", "HIGH", "none")
    }
    await flow.worker().run(job_id)

    row = await recommendation_row(session_factory, rec_id)
    level = row.risk_level or "none"
    assert sample("jobs_total", status="succeeded") == succeeded + 1
    assert sample("recommendations_total", risk_level=level, **partial) == (
        stored_before[level] + 1
    )
    assert sample("safety_gate_overrides_total", rule="R-02") == r02 + 1
    assert sample("safety_gate_overrides_total", rule="R-03") == r03 + 1
    assert sample("agent_request_duration_seconds_count", outcome="success") == calls + 1


async def test_failed_jobs_are_counted_without_service_reports(flow: Flow) -> None:
    flow.agent_state.scenario = "bad_schema"
    failed = sample("jobs_total", status="failed")
    user = await flow.user()
    job_id, _ = await flow.queued_job(new(user))

    await flow.worker().run(job_id)

    assert sample("jobs_total", status="failed") == failed + 1
    assert await flow.redis.exists(flow.keys.service_reports()) == 0
