from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI

from app.api.deps import get_ops_service
from app.core.clock import SystemClock
from app.core.config import Settings
from app.domain.enums import ServiceState
from app.domain.service_status import DATA_SERVICES
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.service_status import RedisServiceStatusStore
from app.services.ops_service import OpsService


class Agent:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy

    async def health(self) -> bool:
        return self.healthy

    async def breaker_state(self) -> str:
        return "closed"


async def up() -> bool:
    return True


async def down() -> bool:
    raise ConnectionError("refused host=postgres.internal")


def use_ops(app: FastAPI, settings: Settings, ops: OpsService) -> None:
    app.dependency_overrides[get_ops_service] = lambda: ops


def ops_with(
    settings: Settings,
    *,
    database: bool = True,
    agent: Agent | None = None,
    store: RedisServiceStatusStore | None = None,
) -> OpsService:
    return OpsService(
        checks={"database": up if database else down, "redis": up},
        agent=agent,
        store=store,
        settings=settings.observability,
        clock=SystemClock(),
    )


@pytest.fixture
async def outside(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """A caller on the public internet (as resolved from trusted proxies)."""
    transport = httpx.ASGITransport(
        app=app, raise_app_exceptions=False, client=("203.0.113.9", 40000)
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def test_ready_when_required_dependencies_answer(
    app: FastAPI, settings: Settings, client: httpx.AsyncClient
) -> None:
    use_ops(app, settings, ops_with(settings, agent=Agent(healthy=False)))

    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok", "agent": "unavailable"},
    }
    assert response.headers["Cache-Control"] == "no-store"


async def test_not_ready_without_database_and_no_details_leak(
    app: FastAPI, settings: Settings, client: httpx.AsyncClient
) -> None:
    use_ops(app, settings, ops_with(settings, database=False))

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] == "unavailable"
    assert "postgres.internal" not in response.text


async def test_ready_without_any_resources_is_not_ready(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {}


@pytest.mark.parametrize("path", ["/ready", "/metrics"])
async def test_ops_endpoints_are_hidden_from_public_callers(
    outside: httpx.AsyncClient, path: str
) -> None:
    response = await outside.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_health_stays_public(outside: httpx.AsyncClient) -> None:
    assert (await outside.get("/health")).status_code == 200


async def test_metrics_use_route_templates(client: httpx.AsyncClient) -> None:
    job_id = uuid4()
    await client.get(f"/v1/jobs/{job_id}")
    await client.get(f"/nowhere/{job_id}")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text
    assert 'http_requests_total{method="GET",route="/v1/jobs/{job_id}",status="401"}' in text
    assert 'route="unmatched"' in text
    assert str(job_id) not in text
    assert "http_request_duration_seconds_bucket" in text


async def test_nested_router_prefixes_are_kept(client: httpx.AsyncClient) -> None:
    feedback_id = uuid4()
    await client.patch(f"/v1/admin/feedback/reviews/{feedback_id}", json={})

    text = (await client.get("/metrics")).text

    assert 'route="/v1/admin/feedback/reviews/{feedback_id}"' in text
    assert str(feedback_id) not in text


async def test_unknown_methods_share_one_label(client: httpx.AsyncClient) -> None:
    await client.request("BREW", "/health")

    text = (await client.get("/metrics")).text

    assert 'method="OTHER"' in text
    assert 'method="BREW"' not in text


async def test_service_status_is_public_and_cached(
    app: FastAPI, settings: Settings, client: httpx.AsyncClient, redis: FakeAsyncRedis
) -> None:
    store = RedisServiceStatusStore(redis, RedisKeys("test"))
    reports = dict.fromkeys(DATA_SERVICES, ServiceState.OK)
    reports["transport"] = ServiceState.DEGRADED
    await store.record(reports, at=SystemClock().now(), ttl_seconds=900)
    use_ops(app, settings, ops_with(settings, agent=Agent(), store=store))

    response = await client.get("/v1/service-status", headers={"Accept-Language": "th"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["api"] == "ok"
    assert body["components"]["agent"] == "ok"
    assert body["components"]["transport"] == "degraded"
    assert body["message"].startswith("บางบริการ")
    assert set(body) == {"status", "updated_at", "components", "message"}
    assert response.headers["Cache-Control"] == "public, max-age=30"


async def test_service_status_message_in_english(
    app: FastAPI, settings: Settings, client: httpx.AsyncClient
) -> None:
    use_ops(app, settings, ops_with(settings, agent=Agent(healthy=False)))

    body = (await client.get("/v1/service-status", headers={"Accept-Language": "en"})).json()

    assert body["status"] == "unavailable"
    assert body["message"] == "Travel analysis is temporarily unavailable."
