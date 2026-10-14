"""GET /health — ห้ามเรียก LLM ในนี้"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "generation",
        "version": settings.git_sha or settings.service_version,
    }
