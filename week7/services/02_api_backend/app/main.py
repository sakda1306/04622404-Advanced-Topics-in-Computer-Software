"""FastAPI application: `uvicorn app.main:app --host 0.0.0.0 --port 8000`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import Container
from app.api.error_handlers import register_error_handlers
from app.api.middleware.body_guard import BodyGuardMiddleware
from app.api.middleware.request_context import RequestContextMiddleware
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.routes import admin, auth, chat, football, health
from app.clients.circuit_breaker import CircuitBreaker
from app.clients.football import FootballDataClient, RetrievalAdminClient
from app.clients.router_client import RouterClient
from app.clients.service_client import ServiceClient
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.infra.store import Store, create_store


def build_container(
    settings: Settings,
    *,
    http: httpx.AsyncClient | None = None,
    store: Store | None = None,
) -> Container:
    engine = create_engine(settings.database_url)
    store = store or create_store(settings.redis_url)
    http = http or httpx.AsyncClient(
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    )
    breaker = CircuitBreaker(
        failure_threshold=settings.breaker_failure_threshold,
        window_seconds=settings.breaker_window_seconds,
        reset_seconds=settings.breaker_reset_seconds,
    )
    return Container(
        settings=settings,
        engine=engine,
        sessions=create_session_factory(engine),
        store=store,
        http=http,
        router=RouterClient(
            http,
            base_url=settings.router_url,
            timeout_seconds=settings.router_timeout_seconds,
            max_retries=settings.router_max_retries,
            breaker=breaker,
        ),
        football=FootballDataClient(
            ServiceClient(
                http,
                base_url=settings.football_data_url,
                timeout_seconds=settings.football_data_timeout_seconds,
                service="football-data",
                unavailable=ErrorCode.FOOTBALL_DATA_UNAVAILABLE,
            ),
            store=store,
            status_ttl_seconds=settings.football_status_cache_seconds,
        ),
        retrieval=RetrievalAdminClient(
            ServiceClient(
                http,
                base_url=settings.retrieval_url,
                timeout_seconds=settings.retrieval_timeout_seconds,
                service="retrieval",
                unavailable=ErrorCode.RETRIEVAL_UNAVAILABLE,
            )
        ),
    )


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json, settings.service_name)
    container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await container.http.aclose()
        await container.store.close()
        await container.engine.dispose()

    app = FastAPI(
        title="Football Assistant API",
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "prod" else None,
        redoc_url=None,
    )
    app.state.container = container

    register_error_handlers(app, type_base_url=settings.error_type_base_url)
    # Added innermost first: the last one added runs first.
    app.add_middleware(
        BodyGuardMiddleware,
        max_body_bytes=settings.max_body_bytes,
        type_base_url=settings.error_type_base_url,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware, type_base_url=settings.error_type_base_url)

    for module in (health, auth, chat, football, admin):
        app.include_router(module.router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `app.main:app` is built on first access so importing this module has no side effects.
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
