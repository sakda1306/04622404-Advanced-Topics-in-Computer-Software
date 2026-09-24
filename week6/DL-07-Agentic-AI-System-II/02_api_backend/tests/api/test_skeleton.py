from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.api.resources import AppResources
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.main import create_app

PROBLEM_KEYS = {
    "type",
    "title",
    "status",
    "code",
    "detail",
    "instance",
    "request_id",
    "correlation_id",
    "errors",
}


class _Body(BaseModel):
    lat: float = Field(ge=-90, le=90)


@pytest.fixture
def app(settings: Settings, resources: AppResources) -> FastAPI:
    app = create_app(settings, resources)

    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("password=hunter2 host=db.internal")

    @app.get("/_test/limited")
    async def limited() -> None:
        raise AppError(ErrorCode.RATE_LIMITED, retry_after=30)

    @app.post("/_test/validate")
    async def validate(body: _Body) -> _Body:
        return body

    return app


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_generates_request_and_correlation_ids(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    request_id = response.headers["X-Request-ID"]
    assert UUID(request_id).version == 7
    assert response.headers["X-Correlation-ID"] == request_id


async def test_propagates_safe_client_ids(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/health", headers={"X-Request-ID": "req-1", "X-Correlation-ID": "corr-1"}
    )

    assert response.headers["X-Request-ID"] == "req-1"
    assert response.headers["X-Correlation-ID"] == "corr-1"


async def test_replaces_unsafe_client_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "bad id <x>"})

    assert response.headers["X-Request-ID"] != "bad id <x>"
    assert UUID(response.headers["X-Request-ID"]).version == 7


async def test_unknown_route_returns_problem_details(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/nope", headers={"X-Request-ID": "req-404"})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert set(body) == PROBLEM_KEYS
    assert body["code"] == "NOT_FOUND"
    assert body["type"] == "https://errors.travel-safety.example/not-found"
    assert body["instance"] == "/v1/nope"
    assert body["request_id"] == "req-404"


async def test_wrong_method_returns_problem_details(client: httpx.AsyncClient) -> None:
    response = await client.post("/health")

    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


async def test_validation_error_lists_fields_without_echoing_input(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/_test/validate", json={"lat": 123.456789})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["errors"][0]["field"] == "lat"
    assert body["errors"][0]["code"] == "less_than_equal"
    assert "123.456789" not in response.text


async def test_malformed_json_is_a_validation_error(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/_test/validate", content=b"{not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_app_error_sets_retry_after(client: httpx.AsyncClient) -> None:
    response = await client.get("/_test/limited")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["code"] == "RATE_LIMITED"


async def test_unexpected_error_hides_internals(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    response = await client.get("/_test/boom", headers={"X-Request-ID": "req-500"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-500"
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["request_id"] == "req-500"
    assert "hunter2" not in response.text
    assert "db.internal" not in response.text
    assert "Traceback" not in response.text
    # The log keeps the error type and request id for debugging.
    logs = capsys.readouterr().out
    assert "unhandled_exception" in logs
    assert "req-500" in logs


async def test_cors_allows_configured_origin_only(client: httpx.AsyncClient) -> None:
    allowed = await client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    denied = await client.options(
        "/health",
        headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "GET"},
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers
    assert "X-Request-ID" in allowed.headers


async def test_docs_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch, resources: AppResources
) -> None:
    monkeypatch.setenv("ENABLE_DOCS", "false")
    app = create_app(Settings(), resources)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        assert (await c.get("/docs")).status_code == 404
        assert (await c.get("/openapi.json")).status_code == 404


async def test_openapi_is_published_when_enabled(client: httpx.AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
