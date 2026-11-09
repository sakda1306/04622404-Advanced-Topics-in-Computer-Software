"""Contract.md §1: request id, Problem-JSON for every error, body limits, health."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException, UploadFile

from tests.conftest import assert_problem


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_request_id_generated_and_echoed(client: httpx.AsyncClient) -> None:
    generated = (await client.get("/api/health")).headers["x-request-id"]
    assert len(generated) == 36
    echoed = await client.get("/api/health", headers={"X-Request-ID": "web-123"})
    assert echoed.headers["x-request-id"] == "web-123"


async def test_unsafe_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert response.headers["x-request-id"] != "bad id\twith spaces"


async def test_unknown_path_is_problem_json(client: httpx.AsyncClient) -> None:
    body = assert_problem(await client.get("/api/nope"), 404, "NOT_FOUND")
    assert "details" not in body


async def test_wrong_method_is_problem_json(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/api/auth/login"), 405, "METHOD_NOT_ALLOWED")


async def test_json_body_too_large(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        content=b'{"email":"' + b"a" * 70_000 + b'"}',
        headers={"content-type": "application/json"},
    )
    assert_problem(response, 413, "PAYLOAD_TOO_LARGE")


async def test_non_json_body_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", content=b"email=a", headers={"content-type": "text/plain"}
    )
    assert_problem(response, 415, "UNSUPPORTED_MEDIA_TYPE")


@pytest.mark.parametrize("settings_overrides", [{"cv_max_bytes": 1024}])
async def test_cv_upload_over_limit(client: httpx.AsyncClient, settings_overrides: Any) -> None:
    response = await client.post(
        "/api/cv", files={"file": ("cv.pdf", b"%PDF" + b"0" * 200_000, "application/pdf")}
    )
    assert_problem(response, 413, "CV_TOO_LARGE")


async def test_thai_text_is_not_escaped(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert "กรุณาเข้าสู่ระบบ".encode() in response.content


def _add_route(app: FastAPI, path: str, endpoint: Any, method: str = "GET") -> None:
    app.add_api_route(path, endpoint, methods=[method])


async def test_unexpected_error_keeps_cors_and_security_headers(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    async def boom() -> None:
        raise RuntimeError("secret detail")

    _add_route(app, "/api/test/boom", boom)
    response = await client.get("/api/test/boom", headers={"Origin": "http://localhost:3000"})
    body = assert_problem(response, 500, "INTERNAL_ERROR")
    assert "secret detail" not in response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-request-id" in response.headers.get("access-control-expose-headers", "").lower()
    assert response.headers["x-content-type-options"] == "nosniff"
    assert body["request_id"]


@pytest.mark.parametrize(("status", "code"), [(400, "BAD_REQUEST"), (409, "HTTP_ERROR")])
async def test_other_http_errors_keep_their_status(
    app: FastAPI, client: httpx.AsyncClient, status: int, code: str
) -> None:
    async def fail() -> None:
        raise HTTPException(status_code=status)

    _add_route(app, "/api/test/fail", fail)
    assert_problem(await client.get("/api/test/fail"), status, code)


async def _chunks(size: int) -> AsyncIterator[bytes]:
    for _ in range(size // 8192 + 1):
        yield b"a" * 8192


async def test_streamed_json_too_large(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", content=_chunks(100_000), headers={"content-type": "application/json"}
    )
    assert "content-length" not in response.request.headers
    assert_problem(response, 413, "PAYLOAD_TOO_LARGE")


@pytest.mark.parametrize("settings_overrides", [{"cv_max_bytes": 1024}])
async def test_streamed_cv_too_large(
    app: FastAPI, client: httpx.AsyncClient, settings_overrides: Any
) -> None:
    async def upload(file: UploadFile) -> dict[str, int]:
        return {"size": len(await file.read())}

    _add_route(app, "/api/cv", upload, method="POST")
    boundary = "b0undary"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="cv.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()

    async def body() -> AsyncIterator[bytes]:
        yield head
        async for chunk in _chunks(200_000):
            yield chunk
        yield f"\r\n--{boundary}--\r\n".encode()

    response = await client.post(
        "/api/cv",
        content=body(),
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    assert_problem(response, 413, "CV_TOO_LARGE")


async def test_non_ascii_content_length(app: FastAPI) -> None:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/auth/login",
        "raw_path": b"/api/auth/login",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", "²".encode("latin-1")),
        ],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    assert sent[0]["status"] == 422


@pytest.mark.parametrize("settings_overrides", [{"environment": "prod"}])
async def test_prod_hides_openapi(client: httpx.AsyncClient, settings_overrides: Any) -> None:
    assert (await client.get("/openapi.json")).status_code == 404
    assert (await client.get("/docs")).status_code == 404


async def test_dev_serves_openapi(client: httpx.AsyncClient) -> None:
    assert (await client.get("/openapi.json")).status_code == 200


# --- found by testing the running system


@pytest.mark.parametrize(
    "body",
    [
        b'{"email":"a@example.com","password":"correct-horse-1","display_name":"a\\u0000b","consent":true}',
        b'{"email":"a@example.com","password":"correct-horse-1","display_name":"a\\ud800b","consent":true}',
        b'{"email":"a@example.com","password":"correct-horse-1","display_name":"a\\udc00b","consent":true}',
    ],
)
async def test_text_the_database_cannot_store_is_a_422(
    client: httpx.AsyncClient, body: bytes
) -> None:
    response = await client.post(
        "/api/auth/register", content=body, headers={"Content-Type": "application/json"}
    )
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_an_escaped_emoji_and_backslash_are_fine(client: httpx.AsyncClient) -> None:
    body = (
        b'{"email":"a@example.com","password":"correct-horse-1",'
        b'"display_name":"a\\ud83d\\ude00\\\\u0000","consent":true}'
    )
    response = await client.post(
        "/api/auth/register", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("url", ["/api/health/%00", "/api/health?x=%00"])
async def test_nul_in_the_url_is_a_422(client: httpx.AsyncClient, url: str) -> None:
    assert_problem(await client.get(url), 422, "VALIDATION_ERROR")
