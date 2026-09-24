"""The whole flow over HTTP: API -> PostGIS/Redis -> inline worker -> mock Agent -> SSE."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import create_app
from tests.conftest import ResourcesFactory, asgi_client
from tests.integration.flow import Flow
from tests.support.auth import TokenFactory

pytestmark = pytest.mark.integration

URL = "/v1/travel/recommendations"


@pytest.fixture
async def client(
    flow: Flow,
    resources_for: ResourcesFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    flow.queue.worker = flow.worker().run
    resources = replace(
        resources_for(flow.settings),
        keys=flow.keys,
        sessions=session_factory,
        job_state=flow.jobs,
        slots=flow.slots,
        tickets=flow.tickets,
        cache=flow.cache,
        queue=flow.queue,
    )
    async with asgi_client(create_app(flow.settings, resources)) as http:
        yield http


def body(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
        "destination": {"lat": 18.7883, "lon": 98.9853, "name": "Chiang Mai"},
        "departure_time": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "timezone": "Asia/Bangkok",
        "language": "en",
        "question": "Is it safe to go?",
    }
    values.update(changes)
    return values


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid4())}


async def test_sync_flow_returns_the_answer(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    token = make_token(subject=f"user-{uuid4()}")

    created = await client.post(URL, json=body(), headers=headers(token))

    assert created.status_code == 200, created.text
    data = created.json()
    assert data["status"] == "completed"
    assert data["recommendation"]["type"] == "TRAVEL_NORMALLY"
    fetched = await client.get(
        f"{URL}/{data['recommendation_id']}", headers={"Authorization": f"Bearer {token}"}
    )
    assert fetched.json() == data


async def test_async_flow_with_sse(
    client: httpx.AsyncClient, make_token: TokenFactory, flow: Flow
) -> None:
    token = make_token(subject=f"user-{uuid4()}")
    auth = {"Authorization": f"Bearer {token}"}

    accepted = await client.post(f"{URL}?mode=async", json=body(), headers=headers(token))
    assert accepted.status_code == 202, accepted.text
    job = accepted.json()
    await flow.queue.drain()
    ticket = (await client.post(f"{job['status_url']}/stream-ticket", headers=auth)).json()
    events = await client.get(f"{job['events_url']}?ticket={ticket['ticket']}")
    status = await client.get(job["status_url"], headers=auth)
    result = await client.get(f"{URL}/{job['recommendation_id']}", headers=auth)

    names = [
        line.split(": ", 1)[1] for line in events.text.splitlines() if line.startswith("event:")
    ]
    assert names[0] == "progress"
    assert names[-1] == "completed"
    assert "assessing_risk" in events.text
    assert status.json()["status"] == "succeeded"
    assert status.json()["progress"] == 100
    assert result.json()["status"] == "completed"
    assert result.json()["conversation_id"] == job["conversation_id"]


async def test_partial_data_never_says_travel_normally(
    client: httpx.AsyncClient, make_token: TokenFactory, flow: Flow
) -> None:
    flow.agent_state.scenario = "partial_disaster_down"

    created = await client.post(
        URL, json=body(), headers=headers(make_token(subject=f"user-{uuid4()}"))
    )

    data = created.json()
    assert data["status"] == "partial_result"
    assert data["recommendation"]["type"] is None
    assert {w["code"] for w in data["warnings"]} >= {"DATA_INCOMPLETE", "SERVICE_DEGRADED"}


async def test_other_users_cannot_read_the_result(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    owner = make_token(subject=f"user-{uuid4()}")
    intruder = {"Authorization": f"Bearer {make_token(subject=f'user-{uuid4()}')}"}
    data = (await client.post(URL, json=body(), headers=headers(owner))).json()

    recommendation = await client.get(f"{URL}/{data['recommendation_id']}", headers=intruder)

    assert recommendation.status_code == 404


async def test_bad_agent_answer_is_502(
    client: httpx.AsyncClient, make_token: TokenFactory, flow: Flow
) -> None:
    flow.agent_state.scenario = "bad_schema"

    created = await client.post(
        URL, json=body(), headers=headers(make_token(subject=f"user-{uuid4()}"))
    )

    assert created.status_code == 502
    assert created.json()["code"] == "AGENT_BAD_RESPONSE"
