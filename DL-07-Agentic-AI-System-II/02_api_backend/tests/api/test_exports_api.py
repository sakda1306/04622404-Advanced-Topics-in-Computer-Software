"""HTTP contract of /v1/me/data-export (the service is faked)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_export_service
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.domain.enums import ExportStatus
from app.main import create_app
from app.services.export_service import ExportView
from app.services.ports import ExportRecord, UserRef
from tests.api.fakes import USER
from tests.conftest import asgi_client
from tests.support.auth import TokenFactory

T0 = datetime(2026, 9, 18, 8, 0, tzinfo=UTC)
URL = "/v1/me/data-export"
READ = ["profile:read"]


def export(status: ExportStatus = ExportStatus.QUEUED, **changes: Any) -> ExportRecord:
    values: dict[str, Any] = {
        "id": new_id(),
        "user_id": USER.id,
        "status": status,
        "object_key": None,
        "created_at": T0,
        "completed_at": None,
        "expires_at": None,
    }
    values.update(changes)
    return ExportRecord(**values)


@dataclass
class FakeExports:
    records: dict[UUID, ExportView] = field(default_factory=dict)
    requested: list[str] = field(default_factory=list)
    limited: bool = False

    async def request(self, user: UserRef, *, correlation_id: str) -> ExportRecord:
        if self.limited:
            raise AppError(ErrorCode.RATE_LIMITED, retry_after=3600)
        self.requested.append(correlation_id)
        made = export()
        self.records[made.id] = ExportView(made, None)
        return made

    async def get(self, user: UserRef, export_id: UUID) -> ExportView:
        found = self.records.get(export_id)
        if found is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return found


@pytest.fixture
def fake() -> FakeExports:
    return FakeExports()


@pytest.fixture
def app(settings: Settings, resources: AppResources, fake: FakeExports) -> FastAPI:
    application = create_app(settings, resources)
    application.dependency_overrides[get_current_user] = lambda: USER
    application.dependency_overrides[get_export_service] = lambda: fake
    return application


def headers(token: str, key: bool = True) -> dict[str, str]:
    values = {"Authorization": f"Bearer {token}"}
    if key:
        values["Idempotency-Key"] = str(uuid4())
    return values


async def test_request_an_export(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeExports
) -> None:
    response = await client.post(URL, headers=headers(make_token(scopes=READ)))

    assert response.status_code == 202, response.text
    body = response.json()
    assert body == {"export_id": body["export_id"], "status": "queued"}
    assert response.headers["Location"] == f"{URL}/{body['export_id']}"
    assert fake.requested


async def test_rules(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeExports
) -> None:
    travel = await client.post(URL, headers=headers(make_token(scopes=["travel:read"])))
    no_key = await client.post(URL, headers=headers(make_token(scopes=READ), key=False))
    fake.limited = True
    limited = await client.post(URL, headers=headers(make_token(scopes=READ)))

    assert travel.status_code == 403
    assert no_key.status_code == 400
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "3600"


async def test_status_and_download_link(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeExports
) -> None:
    ready = export(
        ExportStatus.READY,
        object_key="exports/x.zip",
        completed_at=T0,
        expires_at=T0 + timedelta(days=7),
    )
    fake.records[ready.id] = ExportView(ready, "https://storage.example/exports/x.zip?sig")
    auth = headers(make_token(scopes=READ), key=False)

    found = await client.get(f"{URL}/{ready.id}", headers=auth)
    missing = await client.get(f"{URL}/{uuid4()}", headers=auth)

    assert found.status_code == 200
    assert found.json() == {
        "export_id": str(ready.id),
        "status": "ready",
        "created_at": "2026-09-18T08:00:00Z",
        "completed_at": "2026-09-18T08:00:00Z",
        "expires_at": "2026-09-25T08:00:00Z",
        "download_url": "https://storage.example/exports/x.zip?sig",
    }
    assert missing.status_code == 404


async def test_without_object_storage_export_is_unavailable(
    settings: Settings, resources: AppResources, make_token: TokenFactory
) -> None:
    application = create_app(settings, resources)
    application.dependency_overrides[get_current_user] = lambda: USER
    async with asgi_client(application) as client:
        response = await client.get(
            f"{URL}/{uuid4()}", headers=headers(make_token(scopes=READ), key=False)
        )

    assert response.status_code == 503
