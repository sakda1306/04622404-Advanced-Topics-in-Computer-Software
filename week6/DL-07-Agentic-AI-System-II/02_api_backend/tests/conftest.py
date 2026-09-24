from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator

import httpx
import pytest
from fakeredis import FakeAsyncRedis, FakeServer
from fastapi import FastAPI
from joserfc.jwk import RSAKey

from app.api.resources import AppResources
from app.core.config import Settings, get_settings
from app.core.security import StaticKeyProvider, TokenVerifier
from app.infrastructure.redis.idempotency_store import RedisIdempotencyStore
from app.infrastructure.redis.keys import RedisKeys
from app.infrastructure.redis.rate_limiter import RedisRateLimiter
from app.main import create_app
from tests.support.auth import TokenFactory, generate_signing_key, public_key_set

REQUIRED_ENV = {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://tsa:tsa@localhost:5432/tsa_test",
    "REDIS_URL": "redis://localhost:6379/0",
    "JWT_ISSUER": "http://testserver/dev-issuer",
    "JWT_AUDIENCE": "travel-safety-api",
    "AGENT_SERVICE_URL": "http://mock-agent:8010",
    "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
    "LOG_JSON": "true",
}


@pytest.fixture(autouse=True)
def env(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    # Run from an empty directory so a developer's local .env never leaks into tests.
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def signing_key() -> RSAKey:
    return generate_signing_key()


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(server=FakeServer())


ResourcesFactory = Callable[[Settings], AppResources]


@pytest.fixture
def resources_for(redis: FakeAsyncRedis, signing_key: RSAKey) -> ResourcesFactory:
    """Build app resources for given settings, backed by fakeredis and the test key."""

    def build(settings: Settings) -> AppResources:
        verifier = TokenVerifier(
            StaticKeyProvider(public_key_set(signing_key)),
            issuer=settings.auth.jwt_issuer,
            audience=settings.auth.jwt_audience,
            algorithms=["RS256"],
        )
        return AppResources(
            settings=settings,
            keys=RedisKeys(settings.app.app_env.value),
            token_verifier=verifier,
            rate_limiter=RedisRateLimiter(redis),
            idempotency=RedisIdempotencyStore(redis),
        )

    return build


@pytest.fixture
def resources(settings: Settings, resources_for: ResourcesFactory) -> AppResources:
    return resources_for(settings)


def asgi_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
def make_token(settings: Settings, signing_key: RSAKey) -> TokenFactory:
    return TokenFactory(signing_key, settings.auth.jwt_issuer, settings.auth.jwt_audience)


@pytest.fixture
def app(settings: Settings, resources: AppResources) -> FastAPI:
    return create_app(settings, resources)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with asgi_client(app) as c:
        yield c
