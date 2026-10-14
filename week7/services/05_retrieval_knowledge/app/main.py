"""FastAPI application: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`.

One worker only: the index lives in this process's memory.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.deps import Container, build_container
from app.api.error_handlers import register_error_handlers
from app.api.middleware.body_guard import BodyGuardMiddleware
from app.api.middleware.request_context import RequestContextMiddleware
from app.api.routes import health, index, search
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.search.aliases import keep_aliases_fresh

log = get_logger(__name__)


async def _load_index(container: Container) -> None:
    try:
        await container.index.load()
    except Exception:
        log.exception("index_load_failed")
        return
    snapshot = container.index.snapshot
    log.info(
        "index_ready",
        chunks=snapshot.size if snapshot else 0,
        index_version=snapshot.index_version if snapshot else None,
    )


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json, settings.service_name)
    container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Loaded in the background: /health answers at once, /ready turns 200 when done.
        tasks = [asyncio.create_task(_load_index(container))]
        client: httpx.AsyncClient | None = None
        if settings.football_data_url:
            client = httpx.AsyncClient(
                base_url=settings.football_data_url, timeout=settings.aliases_timeout_seconds
            )
            tasks.append(
                asyncio.create_task(
                    keep_aliases_fresh(
                        container.aliases,
                        client,
                        every=settings.aliases_cache_seconds,
                        retry_after=settings.aliases_retry_seconds,
                    )
                )
            )
        yield
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if client is not None:
            await client.aclose()
        await container.jobs.close()
        # A load or write already in a worker thread still uses the store: let it finish.
        await container.index.drain()
        container.store.close()

    app = FastAPI(
        title="Football Assistant Retrieval",
        version=settings.version,
        lifespan=lifespan,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.container = container

    register_error_handlers(app, type_base_url=settings.error_type_base_url)
    # Added innermost first: the last one added runs first.
    app.add_middleware(
        BodyGuardMiddleware,
        max_body_bytes=settings.max_body_bytes,
        large_paths={"/index/upsert": settings.max_upsert_body_bytes},
        type_base_url=settings.error_type_base_url,
    )
    app.add_middleware(RequestContextMiddleware, type_base_url=settings.error_type_base_url)

    for module in (health, search, index):
        app.include_router(module.router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `app.main:app` is built on first access so importing this module has no side effects.
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
