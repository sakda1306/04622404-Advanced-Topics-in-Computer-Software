"""Test app: SQLite file DB, in-memory store, stub services over in-process transports."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.api.deps import Container
from app.core.config import Settings
from app.db.models import Base
from app.infra.store import MemoryStore
from app.main import build_container, create_app
from app.seed import seed_users
from stubs import football_data_stub, router_stub

ADMIN_PASSWORD = "admin-pass-123"
DEMO_PASSWORD = "demo-pass-123"


class RecordingRouter(httpx.AsyncBaseTransport):
    """The router stub, keeping every RouteRequest body it receives."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._stub = httpx.ASGITransport(app=router_stub.app)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.requests.append(json.loads(request.content))
        return await self._stub.handle_async_request(request)


class DownTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)


class IsolatedSettings(Settings):
    """Only the values given here and the defaults: no env vars, no `.env` file.

    Otherwise a GIT_SHA or rate limit set on the machine (docker compose, CI) leaks in.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        *_sources: PydanticBaseSettingsSource,
        **_kwargs: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        "redis_url": "",
        "jwt_secret_key": "test-secret-key-that-is-long-enough-32",
        "log_level": "WARNING",
        "log_json": False,
        "seed_admin_password": ADMIN_PASSWORD,
        "seed_demo_password": DEMO_PASSWORD,
        "feedback_wait_seconds": 0.3,
        "router_timeout_seconds": 2.0,
    }
    values.update(overrides)
    return IsolatedSettings(**values)


@pytest.fixture(autouse=True)
def _reset_stub_state() -> None:
    football_data_stub.reset_state()


@pytest.fixture
def recording_router() -> RecordingRouter:
    return RecordingRouter()


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    return {}


@pytest.fixture
def football_transport() -> httpx.AsyncBaseTransport:
    return httpx.ASGITransport(app=football_data_stub.app)


@pytest.fixture
async def container(
    tmp_path: Path,
    settings_overrides: dict[str, Any],
    recording_router: RecordingRouter,
    football_transport: httpx.AsyncBaseTransport,
) -> AsyncIterator[Container]:
    settings = make_settings(tmp_path, **settings_overrides)
    http = httpx.AsyncClient(
        mounts={
            "http://router:8000": recording_router,
            "http://football-data:8000": football_transport,
            "http://retrieval:8000": httpx.ASGITransport(app=football_data_stub.app),
        }
    )
    built = build_container(settings, http=http, store=MemoryStore())
    async with built.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with built.sessions() as db:
        await seed_users(db, settings)
    yield built
    await http.aclose()
    await built.engine.dispose()


@pytest.fixture
def app(container: Container) -> FastAPI:
    return create_app(container.settings, container)


ClientFactory = Callable[[], httpx.AsyncClient]


@pytest.fixture
async def client_factory(app: FastAPI) -> AsyncIterator[ClientFactory]:
    clients: list[httpx.AsyncClient] = []

    def make() -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()


async def login(client: httpx.AsyncClient, username: str, password: str) -> httpx.Response:
    response = await client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response


@pytest.fixture
async def client(client_factory: ClientFactory) -> httpx.AsyncClient:
    return client_factory()


@pytest.fixture
async def demo(client_factory: ClientFactory) -> httpx.AsyncClient:
    c = client_factory()
    await login(c, "demo1", DEMO_PASSWORD)
    return c


@pytest.fixture
async def demo2(client_factory: ClientFactory) -> httpx.AsyncClient:
    c = client_factory()
    await login(c, "demo2", DEMO_PASSWORD)
    return c


@pytest.fixture
async def admin(client_factory: ClientFactory) -> httpx.AsyncClient:
    c = client_factory()
    await login(c, "admin", ADMIN_PASSWORD)
    return c


def assert_problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body: dict[str, Any] = response.json()
    assert body["code"] == code
    assert body["status"] == status
    assert body["service"] == "api"
    assert body["request_id"] == response.headers["x-request-id"]
    return body
