"""Authentication, scopes and per-user / per-endpoint rate limits over HTTP."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from fastapi import APIRouter, Depends, FastAPI
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.auth import get_principal, recommend_rate_limit, require_scopes
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.security import Principal, Scope
from app.main import create_app
from tests.conftest import ResourcesFactory, asgi_client
from tests.support.auth import TokenFactory


def _router() -> APIRouter:
    router = APIRouter(prefix="/_test")

    @router.get("/me")
    async def me(principal: Principal = Depends(get_principal)) -> dict[str, Any]:
        return {"sub": principal.subject, "scopes": sorted(principal.scopes)}

    @router.get("/admin")
    async def admin(
        principal: Principal = Depends(require_scopes(Scope.ADMIN_READ)),
    ) -> dict[str, str]:
        return {"sub": principal.subject}

    @router.get("/expensive", dependencies=[Depends(recommend_rate_limit)])
    async def expensive() -> dict[str, bool]:
        return {"ok": True}

    return router


def _build(settings: Settings, resources: AppResources) -> FastAPI:
    app = create_app(settings, resources)
    app.include_router(_router())
    return app


@pytest.fixture
def app(settings: Settings, resources: AppResources) -> FastAPI:
    return _build(settings, resources)


def _client_with(settings: Settings, resources_for: ResourcesFactory) -> httpx.AsyncClient:
    return asgi_client(_build(settings, resources_for(settings)))


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer   "},
        {"Authorization": "Bearer not-a-jwt"},
    ],
)
async def test_missing_or_invalid_credentials_are_401(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get("/_test/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    assert response.headers["content-type"] == "application/problem+json"


async def test_expired_token_is_401(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    from datetime import UTC, datetime, timedelta

    old = datetime.now(UTC) - timedelta(hours=1)

    response = await client.get("/_test/me", headers=bearer(make_token(now=old)))

    assert response.status_code == 401
    assert 'error="invalid_token"' in response.headers["WWW-Authenticate"]


async def test_token_is_not_echoed_in_errors_or_logs(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    token = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzZWNyZXQtdXNlciJ9.c2lnbmF0dXJl"

    response = await client.get("/_test/me", headers=bearer(token))

    assert response.status_code == 401
    assert token not in response.text
    assert token not in capsys.readouterr().out


# ------------------------------------------------------------------ 200 / 403


async def test_valid_token_reaches_the_endpoint(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    response = await client.get("/_test/me", headers=bearer(make_token("user-7", ["travel:read"])))

    assert response.status_code == 200
    assert response.json() == {"sub": "user-7", "scopes": ["travel:read"]}
    assert response.headers["RateLimit-Limit"] == "60"  # P-30
    assert response.headers["RateLimit-Remaining"] == "59"


async def test_missing_scope_is_403(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    response = await client.get("/_test/admin", headers=bearer(make_token()))

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert 'error="insufficient_scope"' in response.headers["WWW-Authenticate"]
    assert 'scope="admin:read"' in response.headers["WWW-Authenticate"]


async def test_required_scope_is_accepted(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    response = await client.get("/_test/admin", headers=bearer(make_token(scopes=["admin:read"])))

    assert response.status_code == 200


# ------------------------------------------------------------------ 429


async def test_per_user_limit(
    monkeypatch: pytest.MonkeyPatch, make_token: TokenFactory, resources_for: ResourcesFactory
) -> None:
    monkeypatch.setenv("RATE_LIMIT_USER", "2")
    async with _client_with(Settings(), resources_for) as client:
        alice = bearer(make_token("alice"))
        codes = [(await client.get("/_test/me", headers=alice)).status_code for _ in range(3)]
        bob = await client.get("/_test/me", headers=bearer(make_token("bob")))
        blocked = await client.get("/_test/me", headers=alice)

    assert codes == [200, 200, 429]
    assert bob.status_code == 200
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.headers["RateLimit-Remaining"] == "0"


async def test_endpoint_limit_is_tighter_than_user_limit(
    monkeypatch: pytest.MonkeyPatch, make_token: TokenFactory, resources_for: ResourcesFactory
) -> None:
    monkeypatch.setenv("RATE_LIMIT_RECOMMEND", "1")
    async with _client_with(Settings(), resources_for) as client:
        headers = bearer(make_token())
        first = await client.get("/_test/expensive", headers=headers)
        second = await client.get("/_test/expensive", headers=headers)
        other_endpoint = await client.get("/_test/me", headers=headers)

    assert first.status_code == 200
    assert first.headers["RateLimit-Limit"] == "1"
    assert second.status_code == 429
    assert other_endpoint.status_code == 200


async def test_redis_keys_do_not_contain_the_subject(
    client: httpx.AsyncClient, make_token: TokenFactory, redis: FakeAsyncRedis
) -> None:
    await client.get("/_test/me", headers=bearer(make_token("very-identifiable-user")))

    keys = [k.decode() if isinstance(k, bytes) else k for k in await redis.keys("*")]
    assert any(":rl:user:" in key for key in keys)
    assert not any("very-identifiable-user" in key for key in keys)


class _BrokenLimiter:
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> Any:
        raise RedisConnectionError("redis down")


async def test_rate_limit_fails_open_when_redis_is_down(
    settings: Settings, resources: AppResources, make_token: TokenFactory
) -> None:
    resources.rate_limiter = _BrokenLimiter()
    async with asgi_client(_build(settings, resources)) as client:
        response = await client.get("/_test/me", headers=bearer(make_token()))

    assert response.status_code == 200
    assert "RateLimit-Limit" not in response.headers


async def test_rate_limit_can_fail_closed(
    monkeypatch: pytest.MonkeyPatch, resources: AppResources, make_token: TokenFactory
) -> None:
    monkeypatch.setenv("RATE_LIMIT_FAIL_OPEN", "false")
    settings = Settings()
    resources.settings = settings
    resources.rate_limiter = _BrokenLimiter()
    async with asgi_client(_build(settings, resources)) as client:
        response = await client.get("/_test/me", headers=bearer(make_token()))

    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert response.headers["Retry-After"] == "5"
