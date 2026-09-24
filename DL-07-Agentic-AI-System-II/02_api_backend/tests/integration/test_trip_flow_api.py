"""Trips over HTTP: save, assess, change, list assessments, delete."""

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


def trip_body() -> dict[str, object]:
    return {
        "name": "North",
        "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
        "destination": {"lat": 18.7883, "lon": 98.9853, "name": "Chiang Mai"},
        "departure_time": when(),
        "timezone": "Asia/Bangkok",
        "alerts": {"enabled": True, "consent_at": datetime.now(UTC).isoformat()},
    }


async def test_trip_lifecycle(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    auth = {"Authorization": f"Bearer {make_token(subject=f'user-{uuid4()}')}"}

    def write() -> dict[str, str]:
        return {**auth, "Idempotency-Key": str(uuid4())}

    created = await client.post("/v1/trips", json=trip_body(), headers=write())
    assert created.status_code == 201, created.text
    url = created.headers["Location"]
    assert created.json()["alerts"]["enabled"] is True

    assessed = await client.post(f"{url}/assessments", json={"language": "en"}, headers=write())
    assert assessed.status_code == 200, assessed.text
    recommendation_id = assessed.json()["recommendation_id"]

    trip = (await client.get(url, headers=auth)).json()
    assert trip["last_assessment"]["recommendation_id"] == recommendation_id
    assert trip["last_assessment"]["outdated"] is False

    moved = await client.patch(
        url,
        json={"departure_time": when(3), "alerts": {"enabled": False}},
        headers={**auth, "Content-Type": "application/merge-patch+json"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["last_assessment"]["outdated"] is True
    assert moved.json()["alerts"] == {"enabled": False, "consent_at": None, "channels": ["IN_APP"]}

    history = (await client.get(f"{url}/assessments", headers=auth)).json()
    assert [i["recommendation_id"] for i in history["items"]] == [recommendation_id]
    listed = (await client.get("/v1/trips", headers=auth)).json()
    assert [t["trip_id"] for t in listed["items"]] == [created.json()["trip_id"]]

    assert (await client.delete(url, headers=auth)).status_code == 204
    assert (await client.get(url, headers=auth)).status_code == 404
    kept = await client.get(f"/v1/travel/recommendations/{recommendation_id}", headers=auth)
    assert kept.status_code == 200


async def test_invalid_trip_is_422(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    auth = {"Authorization": f"Bearer {make_token(subject=f'user-{uuid4()}')}"}
    body = trip_body() | {"alerts": {"enabled": True}, "timezone": "Mars/Base"}

    response = await client.post(
        "/v1/trips", json=body, headers={**auth, "Idempotency-Key": str(uuid4())}
    )

    assert response.status_code == 422
    assert {e["field"] for e in response.json()["errors"]} == {"alerts.consent_at", "timezone"}


async def test_another_users_trip_is_hidden(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    owner = {"Authorization": f"Bearer {make_token(subject=f'user-{uuid4()}')}"}
    intruder = {"Authorization": f"Bearer {make_token(subject=f'user-{uuid4()}')}"}
    url = (
        await client.post(
            "/v1/trips", json=trip_body(), headers={**owner, "Idempotency-Key": str(uuid4())}
        )
    ).headers["Location"]

    assert (await client.get(url, headers=intruder)).status_code == 404
    assert (await client.patch(url, json={"name": "x"}, headers=intruder)).status_code == 404
    assert (await client.get(f"{url}/assessments", headers=intruder)).status_code == 404
    assessed = await client.post(
        f"{url}/assessments", json={}, headers={**intruder, "Idempotency-Key": str(uuid4())}
    )
    assert assessed.status_code == 404
    assert (await client.delete(url, headers=intruder)).status_code == 404
    assert (await client.get("/v1/trips", headers=intruder)).json()["items"] == []
