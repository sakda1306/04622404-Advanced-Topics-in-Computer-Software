from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi import APIRouter, Depends
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.auth import get_principal
from app.api.idempotency import IdempotentRoute
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.security import JWKSKeyProvider, Principal
from app.main import create_app
from tests.conftest import asgi_client
from tests.support.auth import TokenFactory


async def test_lifespan_builds_and_closes_resources(settings: Settings) -> None:
    app = create_app(settings)
    assert app.state.resources is None

    async with app.router.lifespan_context(app):
        built = app.state.resources
        assert isinstance(built, AppResources)
        assert isinstance(built.token_verifier._keys, JWKSKeyProvider)
        assert built.redis is not None
        assert built.http is not None
        http = built.http

    assert http.is_closed


async def test_lifespan_keeps_injected_resources(
    settings: Settings, resources: AppResources
) -> None:
    app = create_app(settings, resources)

    async with app.router.lifespan_context(app):
        assert app.state.resources is resources


class _FlakyStore:
    """Starts normally but cannot store or release (Redis dropped mid-request)."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    async def begin(self, *args: Any, **kwargs: Any) -> Any:
        return await self.inner.begin(*args, **kwargs)

    async def complete(self, *args: Any, **kwargs: Any) -> bool:
        raise RedisConnectionError("down")

    async def release(self, *args: Any, **kwargs: Any) -> None:
        raise RedisConnectionError("down")


@pytest.mark.parametrize(("fail", "status"), [(False, 201), (True, 409)])
async def test_store_errors_after_the_work_do_not_fail_the_request(
    settings: Settings,
    resources: AppResources,
    make_token: TokenFactory,
    fail: bool,
    status: int,
) -> None:
    resources.idempotency = _FlakyStore(resources.idempotency)
    router = APIRouter(route_class=IdempotentRoute)

    @router.post("/_test/x", status_code=201)
    async def create(principal: Principal = Depends(get_principal)) -> dict[str, str]:
        if fail:
            from app.core.errors import AppError, ErrorCode

            raise AppError(ErrorCode.JOB_NOT_CANCELLABLE)
        return {"ok": "yes"}

    app = create_app(settings, resources)
    app.include_router(router)
    async with asgi_client(app) as client:
        response = await client.post(
            "/_test/x",
            json={},
            headers={"Authorization": f"Bearer {make_token()}", "Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == status
