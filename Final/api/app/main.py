"""FastAPI application: `uvicorn app.main:app --host 0.0.0.0 --port 8000`."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import Container
from app.api.error_handlers import register_error_handlers
from app.api.middleware.body_guard import BodyGuardMiddleware
from app.api.middleware.quota_headers import QuotaHeadersMiddleware
from app.api.middleware.request_context import RequestContextMiddleware
from app.api.middleware.request_log import RequestLogMiddleware
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.middleware.unhandled_errors import UnhandledErrorMiddleware
from app.api.routes import admin, auth, chat, cv, health, profile, questionnaire, quota, roles
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.infra.db import create_engine, create_session_factory
from app.infra.jev import build_jev
from app.infra.llm import GroqClient
from app.infra.rate_limit import AttemptLimiter
from app.rag.knowledge import Knowledge
from app.services import log_cleanup, market_refresh


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    return Container(
        settings=settings,
        engine=engine,
        sessions=sessions,
        login_limiter=AttemptLimiter(settings.login_failures_per_minute),
        llm=GroqClient(settings, sessions),
        knowledge=Knowledge(),
        jev=build_jev(settings, sessions),
    )


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # A daemon thread: a slow model download must not hold up start-up or shutdown.
        threading.Thread(
            target=container.knowledge.load, args=(settings,), name="rag-load", daemon=True
        ).start()
        jobs = [
            asyncio.create_task(log_cleanup.run_daily(container.sessions, settings)),
            asyncio.create_task(market_refresh.run_daily(container.sessions, settings)),
        ]
        yield
        for job in jobs:
            job.cancel()
            with suppress(asyncio.CancelledError):
                await job
        await container.llm.aclose()
        if container.jev is not None:
            await container.jev.aclose()
        await container.engine.dispose()

    is_prod = settings.environment == "prod"
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.version,
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        openapi_url=None if is_prod else "/openapi.json",
        redoc_url=None,
    )
    app.state.container = container

    register_error_handlers(app, type_base_url=settings.error_type_base_url)
    # Added innermost first: the last one added runs first.
    app.add_middleware(QuotaHeadersMiddleware)
    app.add_middleware(UnhandledErrorMiddleware, type_base_url=settings.error_type_base_url)
    app.add_middleware(
        BodyGuardMiddleware,
        max_json_bytes=settings.max_json_bytes,
        max_upload_bytes=settings.cv_max_bytes,
        type_base_url=settings.error_type_base_url,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=[
            "X-Request-ID",
            "Retry-After",
            "X-Quota-Requests-Remaining",
            "X-Quota-Tokens-Remaining",
            "X-Quota-Reset",
        ],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RequestContextMiddleware, type_base_url=settings.error_type_base_url)

    for module in (health, auth, cv, questionnaire, quota, chat, profile, roles, admin):
        app.include_router(module.router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `app.main:app` is built on first access so importing this module has no side effects.
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
