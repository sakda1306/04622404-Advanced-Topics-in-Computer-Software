"""FastAPI app entrypoint — service 06 · LLM Generation"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.errors import register_error_handlers
from app.middleware import RequestIDMiddleware, log_event
from app.routes import generate, health, report


@asynccontextmanager
async def lifespan(app: FastAPI):
    # เดิม get_llm_client() ใน routes/generate.py สร้าง RealLLMClient ใหม่ทุก request
    # (ซึ่งข้างในสร้าง AsyncOpenAI/httpx client ใหม่ทุกครั้งด้วย) ไม่มีใครปิด
    # connection เลย เสี่ยง socket leak เมื่อโหลดสูง — สร้างครั้งเดียวตอน startup
    # เก็บไว้ที่ app.state ให้ routes ใช้ร่วมกัน แล้วปิดตอน shutdown
    if not settings.llm_mock:
        from app.llm.client import RealLLMClient

        app.state.llm_client = RealLLMClient(settings)
        asyncio.create_task(app.state.llm_client.check_models_available())
    else:
        app.state.llm_client = None

    log_event("startup", "-", service="generation", version=settings.service_version)
    yield

    llm_client = getattr(app.state, "llm_client", None)
    if llm_client is not None:
        await llm_client.aclose()
    log_event("shutdown", "-", service="generation")


app = FastAPI(title="06 · LLM Generation", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)
register_error_handlers(app)

app.include_router(health.router)
app.include_router(generate.router)
app.include_router(report.router)
