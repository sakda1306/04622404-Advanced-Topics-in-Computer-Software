"""Test app on a temporary SQLite file, isolated from env vars and `.env`."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.api.deps import Container
from app.core.config import Settings
from app.infra.db import Base
from app.main import build_container, create_app

PASSWORD = "correct-horse-1"


class IsolatedSettings(Settings):
    """Only the values given here and the defaults: no env vars, no `.env` file."""

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
        "database_url": f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        "jwt_secret": "test-secret-key-that-is-long-enough-32",
        "log_level": "WARNING",
        "log_json": False,
    }
    values.update(overrides)
    return IsolatedSettings(**values)


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    return {}


@pytest.fixture
async def container(tmp_path: Path, settings_overrides: dict[str, Any]) -> AsyncIterator[Container]:
    built = build_container(make_settings(tmp_path, **settings_overrides))
    async with built.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield built
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


@pytest.fixture
async def client(client_factory: ClientFactory) -> httpx.AsyncClient:
    return client_factory()


async def register(
    client: httpx.AsyncClient, email: str = "user@example.com", password: str = PASSWORD
) -> httpx.Response:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "ผู้ใช้", "consent": True},
    )
    assert response.status_code == 200, response.text
    return response


@pytest.fixture
async def user(client_factory: ClientFactory) -> httpx.AsyncClient:
    c = client_factory()
    await register(c)
    return c


def assert_problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body: dict[str, Any] = response.json()
    assert body["code"] == code
    assert body["status"] == status
    assert body["message_th"]
    assert body["type"].endswith("/" + code.lower().replace("_", "-"))
    assert body["request_id"] == response.headers["x-request-id"]
    return body
