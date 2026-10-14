"""GET /health (CONTRACT §0) and GET /ready (index loaded; the compose healthcheck)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import ContainerDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(container: ContainerDep) -> dict[str, str]:
    settings = container.settings
    return {"status": "ok", "service": settings.service_name, "version": settings.version}


@router.get("/ready")
async def ready(container: ContainerDep) -> JSONResponse:
    snapshot = container.index.snapshot
    if snapshot is None:
        return JSONResponse(
            {"status": "loading", "chunks": 0, "index_version": None}, status_code=503
        )
    return JSONResponse(
        {"status": "ok", "chunks": snapshot.size, "index_version": snapshot.index_version}
    )
