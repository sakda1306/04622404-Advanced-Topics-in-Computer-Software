"""HTTP contract of /v1/me (the service is faked)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.api.auth import principal_key
from app.api.deps import get_current_user, get_me_service
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.security import Principal
from app.main import create_app
from tests.api.fakes import USER, FakeMe
from tests.support.auth import TokenFactory

URL = "/v1/me"


@pytest.fixture
def fake() -> FakeMe:
    return FakeMe()


@pytest.fixture
def app(settings: Settings, resources: AppResources, fake: FakeMe) -> FastAPI:
    application = create_app(settings, resources)
    application.dependency_overrides[get_current_user] = lambda: USER
    application.dependency_overrides[get_me_service] = lambda: fake
    return application


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_get_profile(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeMe
) -> None:
    response = await client.get(
        URL, headers=bearer(make_token(scopes=["profile:read"], email="sakda@example.com"))
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "user_id": str(USER.id),
        "display_name": "Sakda",
        "email_masked": "s***@example.com",
        "language": "th",
        "timezone": "Asia/Bangkok",
        "home_region": "TH",
        "consents": {"live_alerts": True, "analytics": False},
        "created_at": "2026-09-17T08:00:00Z",
    }
    assert fake.calls == [("get", {"email": "sakda@example.com"})]


async def test_scopes(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    travel_only = bearer(make_token(scopes=["travel:read", "travel:write"]))
    read_only = bearer(make_token(scopes=["profile:read"]))

    assert (await client.get(URL, headers=travel_only)).status_code == 403
    assert (await client.patch(URL, json={"language": "en"}, headers=read_only)).status_code == 403
    assert (await client.delete(URL, headers=read_only)).status_code == 403


async def test_patch_profile(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeMe
) -> None:
    response = await client.patch(
        URL,
        content=b'{"language": "en", "home_region": null, "consents": {"analytics": true}}',
        headers={
            **bearer(make_token(scopes=["profile:write"])),
            "Content-Type": "application/merge-patch+json",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["language"] == "en"
    assert body["home_region"] is None
    assert body["consents"] == {"live_alerts": True, "analytics": True}
    assert body["email_masked"] is None
    _, kwargs = fake.calls[-1]
    assert kwargs["changes"].explicit_nulls == frozenset({"home_region"})
    assert kwargs["correlation_id"]
    assert len(kwargs["ip_hash"]) == 64


@pytest.mark.parametrize(
    "bad",
    [
        {"favourite": "tea"},
        {"consents": {"marketing": True}},
        {"language": None},
        {"language": "fr"},
    ],
)
async def test_bad_patch_is_422(
    client: httpx.AsyncClient, make_token: TokenFactory, bad: dict[str, object]
) -> None:
    response = await client.patch(
        URL, json=bad, headers=bearer(make_token(scopes=["profile:write"]))
    )

    assert response.status_code == 422


async def test_delete_account(
    client: httpx.AsyncClient,
    make_token: TokenFactory,
    fake: FakeMe,
    resources: AppResources,
    settings: Settings,
) -> None:
    token = make_token(subject="alice", scopes=["profile:write"])

    response = await client.delete(URL, headers=bearer(token))

    assert response.status_code == 202
    assert response.json() == {"status": "deleting"}
    _, kwargs = fake.calls[-1]
    principal = Principal(
        subject="alice",
        issuer=settings.auth.jwt_issuer,
        scopes=frozenset(),
        expires_at=datetime.now(UTC),
    )
    assert kwargs["principal_hash"] == principal_key(resources, principal)
