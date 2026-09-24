"""Body guard (413/415), security headers and the per-IP rate limit."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY

from app.api.resources import AppResources
from app.core.config import Settings
from app.main import create_app
from tests.conftest import ResourcesFactory, asgi_client


@pytest.fixture
def app(settings: Settings, resources: AppResources) -> FastAPI:
    app = create_app(settings, resources)

    @app.post("/_test/echo")
    async def echo(body: dict[str, object]) -> dict[str, int]:
        return {"keys": len(body)}

    return app


# ------------------------------------------------------------------ 413 / 415


async def test_declared_oversized_body_is_413(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/_test/echo",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": str(64 * 1024 + 1)},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


async def test_streamed_oversized_body_is_413(client: httpx.AsyncClient) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"a":"'
        for _ in range(70):
            yield b"x" * 1024
        yield b'"}'

    response = await client.post(
        "/_test/echo", content=chunks(), headers={"content-type": "application/json"}
    )

    assert "content-length" not in response.request.headers
    assert response.status_code == 413


async def test_body_at_the_limit_is_accepted(client: httpx.AsyncClient) -> None:
    padding = 64 * 1024 - len(b'{"a":""}')
    body = b'{"a":"' + b"x" * padding + b'"}'

    response = await client.post(
        "/_test/echo", content=body, headers={"content-type": "application/json"}
    )

    assert len(body) == 64 * 1024
    assert response.status_code == 200


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", ""])
async def test_non_json_body_is_415(client: httpx.AsyncClient, content_type: str) -> None:
    response = await client.post(
        "/_test/echo", content=b"a=1", headers={"content-type": content_type}
    )

    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.parametrize(
    "content_type",
    ["application/json; charset=utf-8", "application/merge-patch+json", "application/vnd.x+json"],
)
async def test_json_media_types_are_accepted(client: httpx.AsyncClient, content_type: str) -> None:
    response = await client.post(
        "/_test/echo", content=b'{"a":1}', headers={"content-type": content_type}
    )

    assert response.status_code == 200


async def test_invalid_content_length_is_400(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/_test/echo",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "abc"},
    )

    assert response.status_code == 400


async def test_post_without_body_is_not_blocked(client: httpx.AsyncClient) -> None:
    response = await client.post("/health")

    assert response.status_code == 405


async def test_guard_errors_still_carry_request_ids(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/_test/echo", content=b"x", headers={"content-type": "text/plain", "X-Request-ID": "r-1"}
    )

    assert response.headers["X-Request-ID"] == "r-1"
    assert response.json()["request_id"] == "r-1"


# ------------------------------------------------------------------ security headers


async def test_security_headers_on_api_responses(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
    assert (
        response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    )
    assert "Strict-Transport-Security" not in response.headers


async def test_security_headers_on_error_responses(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope")

    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"


async def test_docs_are_not_blocked_by_csp(client: httpx.AsyncClient) -> None:
    response = await client.get("/docs")

    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_hsts_is_sent_in_production(
    monkeypatch: pytest.MonkeyPatch, resources_for: ResourcesFactory
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("PSEUDONYM_SECRET", "p" * 32)
    monkeypatch.setenv("IP_HASH_SECRET", "i" * 32)
    monkeypatch.setenv("COLUMN_ENCRYPTION_KEYS", "k1:" + "a" * 43 + "=")
    settings = Settings()
    async with asgi_client(create_app(settings, resources_for(settings))) as client:
        response = await client.get("/health")

    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")


# ------------------------------------------------------------------ IP rate limit


async def test_ip_limit_returns_429_with_retry_after(
    monkeypatch: pytest.MonkeyPatch, resources_for: ResourcesFactory
) -> None:
    monkeypatch.setenv("RATE_LIMIT_IP", "2")
    settings = Settings()
    refused = REGISTRY.get_sample_value("rate_limit_hits_total", {"scope": "ip"}) or 0.0
    async with asgi_client(create_app(settings, resources_for(settings))) as client:
        codes = [(await client.get("/nope")).status_code for _ in range(3)]
        blocked = await client.get("/docs", headers={"X-Request-ID": "r-429"})
        health = await client.get("/health")
        preflight = await client.options(
            "/nope",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )

    assert codes == [404, 404, 429]
    assert REGISTRY.get_sample_value("rate_limit_hits_total", {"scope": "ip"}) == refused + 2
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert blocked.json()["request_id"] == "r-429"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.headers["RateLimit-Limit"] == "2"
    assert blocked.headers["X-Content-Type-Options"] == "nosniff"
    assert health.status_code == 200
    assert preflight.status_code == 200


async def test_ip_limit_is_keyed_by_hashed_ip(client: httpx.AsyncClient, redis: object) -> None:
    await client.get("/nope")

    keys = [key.decode() for key in await redis.keys("*")]  # type: ignore[attr-defined]
    ip_keys = [key for key in keys if ":rl:ip:" in key]
    assert len(ip_keys) == 1
    assert "127.0.0.1" not in ip_keys[0]


async def test_production_requires_hash_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(ValidationError, match="PSEUDONYM_SECRET, IP_HASH_SECRET"):
        Settings()
