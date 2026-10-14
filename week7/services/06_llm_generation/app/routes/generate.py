"""POST /generate — router(03) เรียก"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.errors import AppValidationError, sanitize_request_id
from app.llm.client import LLMClient
from app.llm.mock import MockLLMClient
from app.pipeline.grounded import run_grounded
from app.pipeline.passthrough import run_passthrough
from app.schemas import GenerateRequest, GenerateResponse

router = APIRouter()


def get_llm_client(request: Request) -> LLMClient:
    """คืน client ที่แชร์กันทั้ง app (สร้างครั้งเดียวตอน startup ใน main.py lifespan)
    เดิมสร้าง RealLLMClient ใหม่ทุก request ทำให้ connection ไม่ถูกปิดเลย
    """
    if settings.llm_mock:
        return MockLLMClient()
    return request.app.state.llm_client


def resolve_request_id(body_request_id: str | None, request: Request) -> str:
    """Header X-Request-ID > body.request_id > UUID ใหม่ (หัวข้อ 4.1)

    เดิมค่านี้ถูกใช้แค่กับ response สำเร็จ (200) เท่านั้น ส่วน error response
    (4xx/5xx) ที่สร้างจาก exception handler ใน errors.py อ่านจาก
    request.state.request_id ซึ่งเป็นค่าที่ middleware ตั้งไว้ตั้งแต่ต้น (ก่อนรู้จัก
    body.request_id) ทำให้ error response ได้ request_id คนละตัวกับ success response
    เวลา client ส่ง request_id มาทาง body ไม่ใช่ header — ผู้เรียกฟังก์ชันนี้ต้อง
    เซ็ต request.state.request_id ด้วยค่าที่ได้กลับมา (ดูจุดเรียกด้านล่าง)

    body_request_id ถูก sanitize ก่อนใช้ — ถ้ามีตัวอักษรนอก latin-1 (เช่นภาษาไทย)
    Starlette จะ encode เป็น HTTP header ไม่ได้ ทำให้ response พังกลางทาง จึงต้อง
    ตกกลับไปสร้าง UUID ใหม่แทนถ้าค่าที่ client ส่งมาใช้เป็น header ไม่ได้
    """
    header_rid = request.headers.get("X-Request-ID")
    if header_rid:
        return header_rid
    safe_body_rid = sanitize_request_id(body_request_id)
    if safe_body_rid:
        return safe_body_rid
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


@router.post("/generate", response_model=GenerateResponse)
async def generate(body: GenerateRequest, request: Request, response: Response):
    request_id = resolve_request_id(body.request_id, request)
    # sync กับ request.state ทันที เพื่อให้ error handler (errors.py) เห็นค่าเดียวกัน
    # ถ้า pipeline ด้านล่างพังกลางทาง (เช่น LLMUnavailable -> 503)
    request.state.request_id = request_id
    response.headers["X-Request-ID"] = request_id
    llm = get_llm_client(request)

    if body.mode == "grounded":
        return await run_grounded(
            body, llm=llm, settings=settings, request_id=request_id
        )
    if body.mode == "passthrough":
        return await run_passthrough(
            body, llm=llm, settings=settings, request_id=request_id
        )
    raise AppValidationError(f"mode ไม่รู้จัก: {body.mode}")
