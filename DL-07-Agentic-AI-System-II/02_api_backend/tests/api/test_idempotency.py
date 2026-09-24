"""Idempotency-Key behaviour of IdempotentRoute (docs/02_api_spec.md section 11.1)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, Response
from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.auth import get_principal
from app.api.idempotency import IdempotentRoute, request_fingerprint
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import Principal
from app.main import create_app
from tests.conftest import asgi_client
from tests.support.auth import TokenFactory


class Item(BaseModel):
    name: str
    size: int = 1


class Calls:
    def __init__(self) -> None:
        self.count = 0


@pytest.fixture
def calls() -> Calls:
    return Calls()


@pytest.fixture
def app(settings: Settings, resources: AppResources, calls: Calls) -> FastAPI:
    router = APIRouter(prefix="/_test", route_class=IdempotentRoute)

    @router.post("/items", status_code=201)
    async def create_item(
        item: Item, response: Response, principal: Principal = Depends(get_principal)
    ) -> dict[str, Any]:
        calls.count += 1
        if item.name == "fail":
            raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        if item.name == "crash":
            raise RuntimeError("boom")
        response.headers["Location"] = f"/_test/items/{calls.count}"
        response.headers["X-Internal"] = "not-replayed"
        return {"id": calls.count, "name": item.name, "owner": principal.subject}

    @router.get("/items")
    async def list_items() -> dict[str, int]:
        return {"count": calls.count}

    app = create_app(settings, resources)
    app.include_router(router)
    return app


def headers(token: str, key: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {token}"}
    if key is not None:
        result["Idempotency-Key"] = key
    return result


def new_key() -> str:
    return str(uuid4())


async def test_key_is_required(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    response = await client.post("/_test/items", json={"name": "a"}, headers=headers(make_token()))

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
    assert "Idempotency-Key" in response.json()["detail"]


@pytest.mark.parametrize("key", ["short", "has space here", "x" * 129, "bad/slash-key"])
async def test_malformed_key_is_rejected(
    client: httpx.AsyncClient, make_token: TokenFactory, key: str
) -> None:
    response = await client.post(
        "/_test/items", json={"name": "a"}, headers=headers(make_token(), key)
    )

    assert response.status_code == 400


@pytest.mark.parametrize("key", [None, new_key(), "bad"])
async def test_authentication_comes_before_idempotency(
    client: httpx.AsyncClient, calls: Calls, key: str | None
) -> None:
    extra = {} if key is None else {"Idempotency-Key": key}
    response = await client.post(
        "/_test/items", json={"name": "a"}, headers={"Authorization": "Bearer bad", **extra}
    )

    assert response.status_code == 401
    assert calls.count == 0


async def test_retry_with_same_key_replays_the_first_response(
    client: httpx.AsyncClient, make_token: TokenFactory, calls: Calls
) -> None:
    h = headers(make_token(), new_key())

    first = await client.post("/_test/items", json={"name": "a", "size": 2}, headers=h)
    second = await client.post("/_test/items", json={"size": 2, "name": "a"}, headers=h)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json() == {"id": 1, "name": "a", "owner": "user-1"}
    assert calls.count == 1
    assert "Idempotent-Replayed" not in first.headers
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.headers["Location"] == "/_test/items/1"
    assert "X-Internal" not in second.headers
    # Response-level middleware still runs on replays.
    assert second.headers["X-Request-ID"] != first.headers["X-Request-ID"]


async def test_same_key_with_different_body_is_409(
    client: httpx.AsyncClient, make_token: TokenFactory, calls: Calls
) -> None:
    h = headers(make_token(), new_key())
    await client.post("/_test/items", json={"name": "a"}, headers=h)

    response = await client.post("/_test/items", json={"name": "b"}, headers=h)

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert calls.count == 1


async def test_keys_are_scoped_per_user(
    client: httpx.AsyncClient, make_token: TokenFactory, calls: Calls
) -> None:
    key = new_key()

    alice = await client.post(
        "/_test/items", json={"name": "a"}, headers=headers(make_token("alice"), key)
    )
    bob = await client.post(
        "/_test/items", json={"name": "b"}, headers=headers(make_token("bob"), key)
    )

    assert alice.status_code == bob.status_code == 201
    assert bob.json()["owner"] == "bob"
    assert calls.count == 2


async def test_different_keys_run_separately(
    client: httpx.AsyncClient, make_token: TokenFactory, calls: Calls
) -> None:
    token = make_token()
    for _ in range(2):
        await client.post("/_test/items", json={"name": "a"}, headers=headers(token, new_key()))

    assert calls.count == 2


@pytest.mark.parametrize(
    ("body", "status"),
    [({"name": "fail"}, 503), ({"name": "crash"}, 500), ({"size": 1}, 422)],
)
async def test_failed_requests_are_not_stored(
    client: httpx.AsyncClient,
    make_token: TokenFactory,
    calls: Calls,
    body: dict[str, Any],
    status: int,
) -> None:
    h = headers(make_token(), new_key())

    first = await client.post("/_test/items", json=body, headers=h)
    retry = await client.post("/_test/items", json=body, headers=h)

    assert first.status_code == retry.status_code == status
    assert "Idempotent-Replayed" not in retry.headers


async def test_client_can_fix_a_failed_request_with_the_same_key(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    h = headers(make_token(), new_key())
    await client.post("/_test/items", json={"name": "fail"}, headers=h)

    response = await client.post("/_test/items", json={"name": "ok"}, headers=h)

    assert response.status_code == 201


async def test_concurrent_duplicate_is_409_in_progress(
    client: httpx.AsyncClient,
    make_token: TokenFactory,
    resources: AppResources,
    calls: Calls,
) -> None:
    key = new_key()
    body = b'{"name":"a"}'
    from app.api.auth import principal_key
    from app.core.security import Principal as P

    # Simulate a request with this key that is still running in another worker.
    owner = P("user-1", resources.settings.auth.jwt_issuer, frozenset(), expires_at=None)  # type: ignore[arg-type]
    store_key = resources.keys.idempotency(
        principal_key(resources, owner), "POST", "/_test/items", key
    )
    await resources.idempotency.begin(
        store_key, request_fingerprint("POST", "/_test/items", body), lock_seconds=60
    )

    response = await client.post(
        "/_test/items",
        content=body,
        headers={**headers(make_token(), key), "content-type": "application/json"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_IN_PROGRESS"
    assert response.headers["Retry-After"] == "2"
    assert calls.count == 0


class _BrokenStore:
    async def begin(self, *args: Any, **kwargs: Any) -> Any:
        raise RedisConnectionError("down")


async def test_store_outage_fails_closed(
    settings: Settings, resources: AppResources, make_token: TokenFactory, calls: Calls
) -> None:
    resources.idempotency = _BrokenStore()  # type: ignore[assignment]
    router = APIRouter(route_class=IdempotentRoute)

    @router.post("/_test/items")
    async def create(principal: Principal = Depends(get_principal)) -> dict[str, str]:
        calls.count += 1
        return {}

    app = create_app(settings, resources)
    app.include_router(router)
    async with asgi_client(app) as client:
        response = await client.post(
            "/_test/items", json={}, headers=headers(make_token(), new_key())
        )

    assert response.status_code == 503
    assert calls.count == 0


async def test_non_post_methods_are_not_affected(client: httpx.AsyncClient) -> None:
    response = await client.get("/_test/items")

    assert response.status_code == 200


def test_fingerprint_ignores_json_key_order_but_not_values() -> None:
    a = request_fingerprint("POST", "/x", b'{"a":1,"b":2}')
    b = request_fingerprint("post", "/x", b'{ "b": 2, "a": 1 }')
    c = request_fingerprint("POST", "/x", b'{"a":1,"b":3}')
    d = request_fingerprint("POST", "/y", b'{"a":1,"b":2}')

    assert a == b
    assert len({a, c, d}) == 3
    assert request_fingerprint("POST", "/x", b"not json") != a
