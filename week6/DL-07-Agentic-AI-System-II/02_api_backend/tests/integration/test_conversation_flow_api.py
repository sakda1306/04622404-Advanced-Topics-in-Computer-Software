"""Conversations over HTTP: create, ask, follow up, read history, delete."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import create_app
from tests.conftest import ResourcesFactory, asgi_client
from tests.integration.flow import Flow
from tests.support.auth import TokenFactory

pytestmark = pytest.mark.integration


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


def when(hours: int = 0) -> str:
    return (datetime.now(UTC) + timedelta(days=2, hours=hours)).isoformat()


async def test_conversation_lifecycle(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    token = make_token(subject=f"user-{uuid4()}")
    auth = {"Authorization": f"Bearer {token}"}

    def write() -> dict[str, str]:
        return {**auth, "Idempotency-Key": str(uuid4())}

    created = await client.post(
        "/v1/conversations", json={"title": "North trip", "language": "en"}, headers=write()
    )
    assert created.status_code == 201, created.text
    url = created.headers["Location"]

    first = await client.post(
        f"{url}/messages",
        json={
            "content": "Is it safe?",
            "overrides": {
                "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
                "destination": {"lat": 18.7883, "lon": 98.9853, "name": "Chiang Mai"},
                "departure_time": when(),
                "timezone": "Asia/Bangkok",
            },
        },
        headers=write(),
    )
    follow_up = await client.post(
        f"{url}/messages",
        json={"content": "And three hours later?", "overrides": {"departure_time": when(3)}},
        headers=write(),
    )
    assert first.status_code == 200, first.text
    assert follow_up.status_code == 200, follow_up.text
    assert follow_up.json()["role"] == "assistant"

    messages = (await client.get(f"{url}/messages", headers=auth)).json()
    assert [m["role"] for m in messages["items"]] == ["assistant", "user", "assistant", "user"]
    assert messages["items"][1]["content"] == "And three hours later?"

    history = (await client.get("/v1/travel/recommendations?limit=1", headers=auth)).json()
    assert history["items"][0]["recommendation_id"] == follow_up.json()["recommendation_id"]
    assert history["next_cursor"]
    older = (
        await client.get(
            f"/v1/travel/recommendations?limit=1&cursor={history['next_cursor']}", headers=auth
        )
    ).json()
    assert older["items"][0]["recommendation_id"] == first.json()["recommendation_id"]

    listed = (await client.get("/v1/conversations", headers=auth)).json()
    assert listed["items"][0]["message_count"] == 4

    deleted = await client.delete(url, headers=auth)
    assert deleted.status_code == 204
    assert (await client.get(url, headers=auth)).status_code == 404
    kept = await client.get(
        f"/v1/travel/recommendations/{first.json()['recommendation_id']}", headers=auth
    )
    assert kept.status_code == 200
    assert kept.json()["conversation_id"] is None


async def test_first_message_without_a_trip_is_422(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    auth = {"Authorization": f"Bearer {make_token(subject=f'user-{uuid4()}')}"}
    url = (
        await client.post(
            "/v1/conversations", json={}, headers={**auth, "Idempotency-Key": str(uuid4())}
        )
    ).headers["Location"]

    response = await client.post(
        f"{url}/messages",
        json={"content": "Is it safe?"},
        headers={**auth, "Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "overrides"


async def test_another_users_conversation_is_hidden(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    owner = {"Authorization": f"Bearer {make_token(subject=f'user-{uuid4()}')}"}
    intruder = {"Authorization": f"Bearer {make_token(subject=f'user-{uuid4()}')}"}
    url = (
        await client.post(
            "/v1/conversations", json={}, headers={**owner, "Idempotency-Key": str(uuid4())}
        )
    ).headers["Location"]

    assert (await client.get(url, headers=intruder)).status_code == 404
    assert (await client.get(f"{url}/messages", headers=intruder)).status_code == 404
    assert (await client.delete(url, headers=intruder)).status_code == 404
    listed = (await client.get("/v1/conversations", headers=intruder)).json()
    assert listed["items"] == []
