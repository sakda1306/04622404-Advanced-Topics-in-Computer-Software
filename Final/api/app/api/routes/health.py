"""Liveness (Contract.md §2.1)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.api.schemas import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(container: ContainerDep) -> Health:
    return Health(version=container.settings.version)
