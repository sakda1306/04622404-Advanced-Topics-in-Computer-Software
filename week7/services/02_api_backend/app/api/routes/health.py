"""GET /health (CONTRACT §0) and GET /ready (database reachable)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import ContainerDep
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/health")
async def health(container: ContainerDep) -> dict[str, str]:
    settings = container.settings
    return {"status": "ok", "service": settings.service_name, "version": settings.version}


@router.get("/ready")
async def ready(container: ContainerDep) -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        async with container.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.warning("ready_database_failed", error_type=type(exc).__name__)
        checks["database"] = "down"
    checks["router_breaker"] = container.router.breaker.state.value
    ok = checks["database"] == "ok"
    return JSONResponse(
        {"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503
    )
