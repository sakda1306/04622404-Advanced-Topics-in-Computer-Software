"""Test settings that ignore the machine's env, an app on the sample KB, Problem-JSON checks."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.api.deps import Container, build_container
from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeEmbedder
from tests.samples import SAMPLE_DOCUMENTS

TEST_DATA = Path(__file__).parent / "data"


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
        "kb_db_path": str(tmp_path / "kb.sqlite"),
        "aliases_file": str(TEST_DATA / "team_aliases.json"),
        # Ingest tests count exact entries; the bundled nickname file is tested on its own.
        "nickname_file": "",
        # No 07 in tests; the alias refresh is tested with a mock transport.
        "football_data_url": "",
        "log_level": "WARNING",
        "log_json": False,
        # No model downloads in unit tests; the real reranker is tested under -m model.
        "rerank_model": "",
    }
    values.update(overrides)
    return IsolatedSettings(**values)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
async def container(settings: Settings, embedder: FakeEmbedder) -> AsyncIterator[Container]:
    built = build_container(settings, embedder=embedder)
    await built.index.upsert(SAMPLE_DOCUMENTS)
    yield built
    built.store.close()


@pytest.fixture
def app(container: Container) -> FastAPI:
    return create_app(container.settings, container)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def unloaded_app(settings: Settings, embedder: FakeEmbedder) -> Iterator[FastAPI]:
    """An app whose index has not finished loading (lifespan does not run under httpx)."""
    built = build_container(settings, embedder=embedder)
    yield create_app(settings, built)
    built.store.close()


def assert_problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body: dict[str, Any] = response.json()
    assert body["code"] == code
    assert body["status"] == status
    assert body["service"] == "retrieval"
    assert body["request_id"] == response.headers["x-request-id"]
    return body
