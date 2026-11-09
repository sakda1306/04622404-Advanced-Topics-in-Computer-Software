"""Contract.md §2.1: register, login, logout, me, delete account."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
import pytest

from tests.conftest import PASSWORD, ClientFactory, assert_problem, register

BANGKOK_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00$")


async def test_register_sets_cookie_and_returns_user(client: httpx.AsyncClient) -> None:
    response = await register(client, email="  New@Example.com ")
    user = response.json()["user"]
    assert user["email"] == "new@example.com"
    assert user["display_name"] == "ผู้ใช้"
    assert BANGKOK_ISO.match(user["created_at"])
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("access_token=")
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert "password_hash" not in response.text


async def test_me_after_register(user: httpx.AsyncClient) -> None:
    response = await user.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "user@example.com"
    assert response.json()["user"]["is_admin"] is False


@pytest.mark.parametrize("settings_overrides", [{"admin_emails": ["admin@example.com"]}])
async def test_admin_email_is_admin_everywhere(client: httpx.AsyncClient) -> None:
    # Contract v0.3d: is_admin is true when the email is in ADMIN_EMAILS.
    registered = await register(client, email="Admin@Example.com")
    assert registered.json()["user"]["is_admin"] is True
    me = await client.get("/api/auth/me")
    assert me.json()["user"]["is_admin"] is True
    login = await client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert login.json()["user"]["is_admin"] is True


@pytest.mark.parametrize("settings_overrides", [{"admin_emails": ["admin@example.com"]}])
async def test_other_email_is_not_admin(user: httpx.AsyncClient) -> None:
    response = await user.get("/api/auth/me")
    assert response.json()["user"]["is_admin"] is False


async def test_me_without_cookie(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/api/auth/me"), 401, "UNAUTHENTICATED")


async def test_me_with_bad_token(client: httpx.AsyncClient) -> None:
    client.cookies.set("access_token", "not-a-jwt")
    assert_problem(await client.get("/api/auth/me"), 401, "UNAUTHENTICATED")


async def test_duplicate_email(client_factory: ClientFactory) -> None:
    await register(client_factory())
    response = await client_factory().post(
        "/api/auth/register",
        json={
            "email": "USER@example.com",
            "password": PASSWORD,
            "display_name": "อีกคน",
            "consent": True,
        },
    )
    assert_problem(response, 409, "EMAIL_TAKEN")


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"consent": False}, "consent"),
        ({"password": "short"}, "password"),
        ({"password": "ก" * 30}, "password"),  # 90 bytes: over the bcrypt limit
        ({"email": "not-an-email"}, "email"),
        ({"display_name": "   "}, "display_name"),
    ],
)
async def test_register_validation(
    client: httpx.AsyncClient, change: dict[str, Any], field: str
) -> None:
    body = {"email": "a@example.com", "password": PASSWORD, "display_name": "A", "consent": True}
    response = await client.post("/api/auth/register", json=body | change)
    problem = assert_problem(response, 422, "VALIDATION_ERROR")
    assert field in [f["field"] for f in problem["details"]["fields"]]
    assert PASSWORD not in response.text


async def test_login_and_logout(client_factory: ClientFactory) -> None:
    await register(client_factory())
    c = client_factory()
    response = await c.post(
        "/api/auth/login", json={"email": "user@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert (await c.get("/api/auth/me")).status_code == 200

    response = await c.post("/api/auth/logout")
    assert response.json() == {"ok": True}
    assert 'access_token=""' in response.headers["set-cookie"]
    assert_problem(await c.get("/api/auth/me"), 401, "UNAUTHENTICATED")


async def test_wrong_password_and_unknown_email_look_the_same(
    client_factory: ClientFactory,
) -> None:
    await register(client_factory())
    c = client_factory()
    wrong = await c.post("/api/auth/login", json={"email": "user@example.com", "password": "x"})
    unknown = await c.post("/api/auth/login", json={"email": "no@example.com", "password": "x"})
    a = assert_problem(wrong, 401, "INVALID_CREDENTIALS")
    b = assert_problem(unknown, 401, "INVALID_CREDENTIALS")
    assert a["message_th"] == b["message_th"]


async def test_login_rate_limited_after_five_failures(client_factory: ClientFactory) -> None:
    await register(client_factory())
    c = client_factory()
    bad = {"email": "user@example.com", "password": "wrong-password"}
    for _ in range(5):
        assert_problem(await c.post("/api/auth/login", json=bad), 401, "INVALID_CREDENTIALS")
    response = await c.post("/api/auth/login", json=bad | {"password": PASSWORD})
    assert_problem(response, 429, "RATE_LIMITED")
    assert int(response.headers["retry-after"]) > 0


async def test_delete_account(client_factory: ClientFactory) -> None:
    c = client_factory()
    await register(c)
    assert_problem(
        await c.request("DELETE", "/api/me", json={"confirm": "yes"}), 422, "VALIDATION_ERROR"
    )

    response = await c.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert_problem(await c.get("/api/auth/me"), 401, "UNAUTHENTICATED")

    # The email is free again.
    await register(client_factory())


async def test_old_token_stops_working_after_delete(client_factory: ClientFactory) -> None:
    c = client_factory()
    await register(c)
    token = c.cookies["access_token"]
    await c.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    other = client_factory()
    other.cookies.set("access_token", token)
    assert_problem(await other.get("/api/auth/me"), 401, "UNAUTHENTICATED")


async def test_parallel_wrong_passwords_cannot_pass_the_limit(
    client_factory: ClientFactory,
) -> None:
    await register(client_factory())
    c = client_factory()
    bad = {"email": "user@example.com", "password": "wrong-password"}
    responses = await asyncio.gather(*(c.post("/api/auth/login", json=bad) for _ in range(20)))
    statuses = sorted(r.status_code for r in responses)
    assert statuses.count(401) == 5
    assert statuses.count(429) == 15


async def test_successful_login_resets_the_count(client_factory: ClientFactory) -> None:
    await register(client_factory())
    c = client_factory()
    bad = {"email": "user@example.com", "password": "wrong-password"}
    for _ in range(4):
        await c.post("/api/auth/login", json=bad)
    good = await c.post("/api/auth/login", json=bad | {"password": PASSWORD})
    assert good.status_code == 200
    for _ in range(5):
        assert_problem(await c.post("/api/auth/login", json=bad), 401, "INVALID_CREDENTIALS")


async def test_health_answers_while_logins_hash(client_factory: ClientFactory) -> None:
    await register(client_factory())
    c = client_factory()
    bad = {"email": "user@example.com", "password": "wrong-password"}
    logins = [asyncio.create_task(c.post("/api/auth/login", json=bad)) for _ in range(4)]
    await asyncio.sleep(0.01)
    health = await c.get("/api/health")
    assert health.status_code == 200
    assert not all(t.done() for t in logins)  # bcrypt still running in threads
    await asyncio.gather(*logins)


@pytest.mark.parametrize("consent", [1, 1.0])
async def test_consent_must_be_the_value_true(client: httpx.AsyncClient, consent: Any) -> None:
    body = {
        "email": "a@example.com",
        "password": PASSWORD,
        "display_name": "A",
        "consent": consent,
    }
    assert_problem(await client.post("/api/auth/register", json=body), 422, "VALIDATION_ERROR")
