"""AgentClient against the Mock Agent over real HTTP semantics (in-process ASGI).

This is the contract both teams agree on (docs/02_api_spec.md section 9): the same
tests can later point at Module 03's service instead of the mock.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from pydantic import SecretStr

from app.core.config import AgentSettings
from app.core.errors import ErrorCode
from app.domain.enums import DataCategory
from app.infrastructure.agent.auth import StaticToken
from app.infrastructure.agent.circuit_breaker import RedisCircuitBreaker
from app.infrastructure.agent.client import AgentCallError, AgentClient, AgentFailure
from app.infrastructure.agent.contracts import AgentRunResponse, ProgressLine
from mock_agent.main import SCENARIOS, MockState, build_result, create_app
from tests.support.agent import run_request

BASE = "http://mock-agent"
SERVICE_TOKEN = "mock-service-token"


class Sleeps:
    async def __call__(self, delay: float) -> None:
        return None


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch) -> MockState:
    monkeypatch.setenv("MOCK_REQUIRE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setenv("MOCK_STEP_DELAY_SECONDS", "0")
    return MockState()


@pytest.fixture
async def http(state: MockState) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(state))
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
        yield client


@pytest.fixture
def agent(http: httpx.AsyncClient, redis: FakeAsyncRedis) -> AgentClient:
    return AgentClient(
        http,
        settings=AgentSettings(agent_service_url=BASE, agent_max_retries=1),
        tokens=StaticToken(SecretStr(SERVICE_TOKEN)),
        breaker=RedisCircuitBreaker(
            redis, name="cb", failure_threshold=10, window_seconds=30, reset_seconds=30
        ),
        sleep=Sleeps(),
    )


def deadline(seconds: float = 30) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


@pytest.mark.parametrize(
    "name",
    sorted(n for n, s in SCENARIOS.items() if "raw_body" not in s and "http" not in s),
)
def test_every_scenario_matches_the_contract(name: str) -> None:
    result = build_result(
        SCENARIOS[name], "0192f0c2-aaaa-7bbb-8ccc-123456789abc", datetime.now(UTC)
    )

    AgentRunResponse.model_validate(result)


@pytest.mark.parametrize(
    ("scenario", "status", "risk", "action"),
    [
        ("low_risk", "completed", "LOW", "TRAVEL_NORMALLY"),
        ("high_risk", "completed", "HIGH", "AVOID_TRAVEL"),
        ("partial_disaster_down", "partial_result", "LOW", "TRAVEL_NORMALLY"),
        ("needs_clarification", "needs_clarification", None, None),
    ],
)
@pytest.mark.parametrize("streaming", [False, True])
async def test_scenarios_over_json_and_ndjson(
    agent: AgentClient,
    state: MockState,
    scenario: str,
    status: str,
    risk: str | None,
    action: str | None,
    streaming: bool,
) -> None:
    state.scenario = scenario
    progress: list[ProgressLine] = []

    async def on_progress(line: ProgressLine) -> None:
        progress.append(line)

    request = run_request()
    result = await agent.run(
        request, deadline=deadline(), on_progress=on_progress if streaming else None
    )

    response = result.response
    assert response.run_id == request.run_id
    assert response.status == status
    assert (response.risk.level if response.risk else None) == risk
    assert (response.recommendation.type if response.recommendation else None) == action
    assert [p.stage for p in progress] == (
        ["fetching_data", "assessing_risk", "generating_advice"] if streaming else []
    )
    sent = state.runs[-1]
    assert sent["headers"]["x-deadline"].endswith("Z")
    assert sent["body"]["run_id"] == str(request.run_id)


async def test_high_risk_scenario_has_emergency_steps(agent: AgentClient, state: MockState) -> None:
    state.scenario = "high_risk"

    response = (await agent.run(run_request(), deadline=deadline())).response

    assert response.emergency_instructions is not None
    assert response.emergency_instructions.contacts[0].phone == "1669"
    assert response.hazards[0].type == "FLOOD"
    assert response.routes is not None
    assert response.routes.alternatives[0].route_id == "r-alt"


async def test_partial_scenario_reports_the_unavailable_service(
    agent: AgentClient, state: MockState
) -> None:
    state.scenario = "partial_disaster_down"

    response = (await agent.run(run_request(), deadline=deadline())).response

    assert response.service_status["disaster"] == "unavailable"
    freshness = {item.category: item.updated_at for item in response.data_freshness.items}
    assert freshness[DataCategory.DISASTER] is None
    assert freshness[DataCategory.WEATHER] is not None


@pytest.mark.parametrize("streaming", [False, True])
async def test_bad_schema_scenario_is_rejected(
    agent: AgentClient, state: MockState, streaming: bool
) -> None:
    state.scenario = "bad_schema"

    async def ignore(line: ProgressLine) -> None:
        return None

    with pytest.raises(AgentCallError) as info:
        await agent.run(
            run_request(), deadline=deadline(), on_progress=ignore if streaming else None
        )

    assert info.value.failure is AgentFailure.BAD_RESPONSE
    assert info.value.to_app_error().code is ErrorCode.AGENT_BAD_RESPONSE


async def test_unavailable_scenario_is_retried_then_503(
    agent: AgentClient, state: MockState
) -> None:
    state.scenario = "unavailable_503"

    with pytest.raises(AgentCallError) as info:
        await agent.run(run_request(), deadline=deadline())

    assert len(state.runs) == 2
    app_error = info.value.to_app_error()
    assert app_error.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert info.value.retry_after == 2


async def test_slow_scenario_hits_the_deadline(agent: AgentClient, state: MockState) -> None:
    state.scenario = "slow_20s"

    with pytest.raises(AgentCallError) as info:
        await agent.run(run_request(), deadline=deadline(0.3))

    assert info.value.failure is AgentFailure.TIMEOUT


async def test_wrong_service_token_is_a_client_error(
    http: httpx.AsyncClient, redis: FakeAsyncRedis
) -> None:
    agent = AgentClient(
        http,
        settings=AgentSettings(agent_service_url=BASE),
        tokens=StaticToken(SecretStr("wrong")),
        breaker=RedisCircuitBreaker(
            redis, name="cb", failure_threshold=10, window_seconds=30, reset_seconds=30
        ),
    )

    with pytest.raises(AgentCallError) as info:
        await agent.run(run_request(), deadline=deadline())

    assert info.value.http_status == 401
    assert info.value.to_app_error().code is ErrorCode.INTERNAL_ERROR


async def test_run_cancelled_on_the_agent_side_is_reported(
    agent: AgentClient, state: MockState
) -> None:
    # ASGITransport buffers whole responses, so a cancel cannot interleave with the
    # stream here; the live test against uvicorn covers that (docker smoke test).
    request = run_request()
    state.cancelled.add(str(request.run_id))

    async def ignore(line: ProgressLine) -> None:
        return None

    with pytest.raises(AgentCallError) as info:
        await agent.run(request, deadline=deadline(), on_progress=ignore)

    assert info.value.failure is AgentFailure.UNAVAILABLE
    assert info.value.attempts[-1].error_code == "CANCELLED"


async def test_cancel_known_run(agent: AgentClient, state: MockState) -> None:
    request = run_request()
    await agent.run(request, deadline=deadline())

    assert await agent.cancel(request.run_id) is True
    assert str(request.run_id) in state.cancelled


async def test_cancel_unknown_run_is_fine(agent: AgentClient) -> None:
    assert await agent.cancel(run_request().run_id) is True


async def test_health(agent: AgentClient) -> None:
    assert await agent.health() is True


# ------------------------------------------------------------------ mock admin API


async def test_scenario_can_be_switched_at_runtime(http: httpx.AsyncClient) -> None:
    listed = (await http.get("/_mock/scenario")).json()
    changed = await http.put("/_mock/scenario", json={"name": "high_risk"})
    unknown = await http.put("/_mock/scenario", json={"name": "nope"})

    assert set(listed["available"]) == set(SCENARIOS)
    assert changed.json() == {"name": "high_risk"}
    assert unknown.status_code == 404
    assert (await http.get("/health")).json()["scenario"] == "high_risk"


@pytest.mark.parametrize(
    ("headers", "body", "status"),
    [
        ({"Authorization": f"Bearer {SERVICE_TOKEN}"}, {"run_id": "x"}, 400),
        (
            {"Authorization": f"Bearer {SERVICE_TOKEN}", "X-Deadline": "2030-01-01T00:00:00Z"},
            {"run_id": "x"},
            422,
        ),
        ({"X-Deadline": "2030-01-01T00:00:00Z"}, {}, 401),
    ],
)
async def test_mock_enforces_the_request_contract(
    http: httpx.AsyncClient, headers: dict[str, str], body: dict[str, Any], status: int
) -> None:
    response = await http.post("/v1/agent/runs", content=json.dumps(body), headers=headers)

    assert response.status_code == status
