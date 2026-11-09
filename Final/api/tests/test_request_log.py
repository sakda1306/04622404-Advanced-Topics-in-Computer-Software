"""`request_log` rows for the admin dashboard (Design.md §2, §4.8, §5)."""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from app.api.deps import Container
from app.infra.models import RequestLog, User
from tests.conftest import register


async def _rows(container: Container, route: str | None = None) -> list[RequestLog]:
    async with container.sessions() as db:
        statement = select(RequestLog).order_by(RequestLog.id)
        if route is not None:
            statement = statement.where(RequestLog.route == route)
        return list(await db.scalars(statement))


async def test_a_successful_request_is_logged(
    container: Container, user: httpx.AsyncClient
) -> None:
    response = await user.get("/api/quota")
    [row] = await _rows(container, "/api/quota")
    assert row.method == "GET"
    assert row.status == 200
    assert row.code is None
    assert row.latency_ms >= 0
    assert row.request_id == response.headers["x-request-id"]
    async with container.sessions() as db:
        expected_user = await db.scalar(select(User.id))
    assert row.user_id == expected_user


async def test_route_is_the_template_without_values(
    container: Container, user: httpx.AsyncClient
) -> None:
    await user.put("/api/questionnaire/answers/ed_level?x=secret", json={"value": "bachelor"})
    [row] = await _rows(container, "/api/questionnaire/answers/{question_id}")
    assert row.method == "PUT"
    stored = " ".join(str(v) for v in vars(row).values())
    assert "ed_level" not in stored
    assert "secret" not in stored
    assert "bachelor" not in stored


async def test_problem_code_is_recorded(container: Container, user: httpx.AsyncClient) -> None:
    await user.put("/api/questionnaire/answers/no_such", json={"value": "x"})
    [row] = await _rows(container, "/api/questionnaire/answers/{question_id}")
    assert (row.status, row.code) == (404, "QUESTION_NOT_FOUND")


async def test_anonymous_request_has_no_user(
    container: Container, client: httpx.AsyncClient
) -> None:
    await client.get("/api/quota")
    [row] = await _rows(container, "/api/quota")
    assert (row.user_id, row.status, row.code) == (None, 401, "UNAUTHENTICATED")


async def test_unknown_path_is_not_stored(container: Container, client: httpx.AsyncClient) -> None:
    await client.get("/api/no/such/secret-path")
    [row] = await _rows(container)
    assert row.route == "(unmatched)"
    assert (row.status, row.code) == (404, "NOT_FOUND")


async def test_rejection_before_routing_is_logged(
    container: Container, client: httpx.AsyncClient
) -> None:
    response = await client.post(
        "/api/auth/login", content="x", headers={"content-type": "text/plain"}
    )
    assert response.status_code == 415
    [row] = await _rows(container)
    assert (row.status, row.code) == (415, "UNSUPPORTED_MEDIA_TYPE")


async def test_unexpected_error_is_logged_as_internal_error(
    app: FastAPI, container: Container, client: httpx.AsyncClient
) -> None:
    async def boom() -> None:
        raise RuntimeError("private detail")

    app.add_api_route("/api/boom", boom)
    response = await client.get("/api/boom")
    assert response.status_code == 500
    [row] = await _rows(container, "/api/boom")
    assert (row.status, row.code) == (500, "INTERNAL_ERROR")


async def test_health_and_docs_are_not_logged(
    container: Container, client: httpx.AsyncClient
) -> None:
    await client.get("/api/health")  # the compose healthcheck would flood the dashboard
    await client.get("/docs")
    assert await _rows(container) == []


async def test_cors_preflight_is_not_logged(
    container: Container, client: httpx.AsyncClient
) -> None:
    response = await client.options(
        "/api/quota",
        headers={"origin": "http://localhost:3000", "access-control-request-method": "GET"},
    )
    assert response.status_code == 200
    assert await _rows(container) == []


async def test_deleting_the_account_removes_its_rows(
    container: Container, user: httpx.AsyncClient
) -> None:
    await user.get("/api/quota")
    response = await user.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert response.status_code == 200, response.text
    rows = await _rows(container)
    assert all(row.user_id is None for row in rows)
    assert await _rows(container, "/api/quota") == []
    # The delete request itself stays, with no link to the user.
    [row] = await _rows(container, "/api/me")
    assert (row.method, row.status, row.user_id) == ("DELETE", 200, None)


async def test_logging_failure_does_not_break_the_response(
    container: Container, client: httpx.AsyncClient
) -> None:
    async with container.engine.begin() as conn:
        await conn.run_sync(RequestLog.__table__.drop)  # type: ignore[arg-type]
    await register(client)  # asserts 200 itself
