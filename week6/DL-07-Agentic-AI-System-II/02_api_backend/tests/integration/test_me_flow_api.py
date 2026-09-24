"""/v1/me and job cancel over HTTP, including the whole account deletion."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.redis.user_data import RedisUserData
from app.main import create_app
from tests.conftest import ResourcesFactory, asgi_client
from tests.integration.flow import Flow
from tests.support.auth import TokenFactory

pytestmark = pytest.mark.integration

ALL = ["travel:read", "travel:write", "profile:read", "profile:write"]


@pytest.fixture
async def client(
    flow: Flow,
    resources_for: ResourcesFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    flow.queue.worker = None  # jobs stay queued, so they can be cancelled
    resources = replace(
        resources_for(flow.settings),
        keys=flow.keys,
        sessions=session_factory,
        job_state=flow.jobs,
        slots=flow.slots,
        tickets=flow.tickets,
        cache=flow.cache,
        queue=flow.queue,
        user_data=RedisUserData(flow.redis, flow.keys),
    )
    async with asgi_client(create_app(flow.settings, resources)) as http:
        yield http


def trip() -> dict[str, object]:
    return {
        "origin": {"lat": 13.7563, "lon": 100.5018},
        "destination": {"lat": 18.7883, "lon": 98.9853},
        "departure_time": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "timezone": "Asia/Bangkok",
    }


async def test_profile_consents_and_cancel(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    auth = {"Authorization": f"Bearer {make_token(subject=f'user-{uuid4()}', scopes=ALL)}"}

    patched = await client.patch(
        "/v1/me", json={"display_name": "Nok", "consents": {"analytics": True}}, headers=auth
    )
    me = (await client.get("/v1/me", headers=auth)).json()
    accepted = await client.post(
        "/v1/travel/recommendations?mode=async",
        json=trip(),
        headers={**auth, "Idempotency-Key": str(uuid4())},
    )
    job_url = accepted.headers["Location"]
    cancelled = await client.delete(job_url, headers=auth)
    again = await client.delete(job_url, headers=auth)
    status = (await client.get(job_url, headers=auth)).json()

    assert patched.status_code == 200, patched.text
    assert me["display_name"] == "Nok"
    assert me["consents"] == {"live_alerts": False, "analytics": True}
    assert accepted.status_code == 202, accepted.text
    assert cancelled.status_code == 202
    assert again.status_code == 409
    assert status["status"] == "cancelled"


async def test_account_deletion(
    client: httpx.AsyncClient, make_token: TokenFactory, flow: Flow
) -> None:
    subject = f"user-{uuid4()}"
    auth = {"Authorization": f"Bearer {make_token(subject=subject, scopes=ALL)}"}
    first = (await client.get("/v1/me", headers=auth)).json()

    deleted = await client.delete("/v1/me", headers=auth)
    blocked = await client.get("/v1/me", headers=auth)
    user_id = flow.queue.deletions[-1][0]
    await flow.account().delete(user_id, correlation_id="corr-task")
    fresh = (await client.get("/v1/me", headers=auth)).json()

    assert deleted.status_code == 202
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "This account is being deleted."
    assert str(user_id) == first["user_id"]
    assert fresh["user_id"] != first["user_id"]
    assert fresh["display_name"] is None
