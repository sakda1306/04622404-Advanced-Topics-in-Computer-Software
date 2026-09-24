"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ops
from app.api.error_handlers import register_error_handlers
from app.api.idempotency import HEADER as IDEMPOTENCY_HEADER
from app.api.idempotency import REPLAYED_HEADER
from app.api.middleware.body_guard import BodyGuardMiddleware
from app.api.middleware.rate_limit import IPRateLimitMiddleware
from app.api.middleware.request_context import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
)
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.openapi import use_custom_openapi
from app.api.resources import AppResources, build_resources
from app.api.v1.router import router as v1_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import instrument_app, setup_tracing

API_TITLE = "Travel Safety & Advisory API"


def create_app(settings: Settings | None = None, resources: AppResources | None = None) -> FastAPI:
    """Build the app. Tests pass `resources`; otherwise they are created at startup."""
    settings = settings or get_settings()
    configure_logging(
        level=settings.observability.log_level,
        json_output=settings.observability.log_json,
    )
    setup_tracing(settings.observability)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = None
        if getattr(app.state, "resources", None) is None:
            owned = build_resources(settings)
            app.state.resources = owned
        log.info("startup", env=settings.app.app_env.value, version=settings.app.api_version)
        try:
            yield
        finally:
            log.info("shutdown")
            if owned is not None:
                await owned.aclose()

    docs = settings.app.enable_docs
    app = FastAPI(
        title=API_TITLE,
        version=settings.app.api_version,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings
    app.state.resources = resources
    use_custom_openapi(app)

    type_base_url = settings.app.error_type_base_url
    register_error_handlers(app, type_base_url=type_base_url)

    # Starlette runs the last added middleware first, so the order below is inner -> outer:
    # body guard, IP rate limit, CORS, security headers, request context.
    app.add_middleware(
        BodyGuardMiddleware,
        max_body_bytes=settings.app.max_body_bytes,
        type_base_url=type_base_url,
    )
    app.add_middleware(IPRateLimitMiddleware, type_base_url=type_base_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept-Language",
            IDEMPOTENCY_HEADER,
            "Last-Event-ID",
            REQUEST_ID_HEADER,
            CORRELATION_ID_HEADER,
        ],
        expose_headers=[
            REQUEST_ID_HEADER,
            CORRELATION_ID_HEADER,
            "Retry-After",
            "RateLimit-Limit",
            "RateLimit-Remaining",
            "RateLimit-Reset",
            REPLAYED_HEADER,
            "Location",
            "WWW-Authenticate",
        ],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.app.is_production)
    app.add_middleware(RequestContextMiddleware, type_base_url=type_base_url)

    app.include_router(ops.router)
    app.include_router(v1_router)
    instrument_app(app)  # outermost, so the server span covers every middleware
    return app
