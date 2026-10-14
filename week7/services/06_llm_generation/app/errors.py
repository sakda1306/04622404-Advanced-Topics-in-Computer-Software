"""Problem-JSON error handling ตามหัวข้อ 4.1"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

PROBLEM_BASE = "https://errors.football-assistant.local"


class LLMUnavailable(Exception):
    """เมื่อทั้ง provider หลักและสำรองล่ม"""


class AppValidationError(Exception):
    """422 error ที่เกิดจาก business rule (เช่น ref ซ้ำ, draft ว่าง)"""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def sanitize_request_id(rid: str | None) -> str | None:
    """คืน rid เดิมถ้าใช้เป็นค่า HTTP header ได้อย่างปลอดภัย (latin-1 encodable)
    ไม่งั้นคืน None ให้ผู้เรียกสร้าง id ใหม่แทน

    request_id ที่ client ส่งมาทาง body (ไม่ใช่ header) เป็น JSON string จึงเป็น
    unicode อะไรก็ได้ รวมถึงภาษาไทย ถ้าเอาไปตั้งเป็นค่า header ตรง ๆ (X-Request-ID)
    Starlette จะพยายาม encode เป็น latin-1 ตามสเปก HTTP/1.1 แล้ว raise
    UnicodeEncodeError กลางทาง ทำให้ response พัง และถ้า error handler (ด้านล่าง)
    พยายามตั้ง header เดิมซ้ำอีกก็จะพังซ้ำเป็น loop ได้ — กรองตรงนี้ครั้งเดียว
    ใช้ร่วมกันทั้งฝั่ง success (routes/generate.py) และฝั่ง error (ไฟล์นี้)
    """
    if not rid:
        return None
    try:
        rid.encode("latin-1")
    except UnicodeEncodeError:
        return None
    return rid


async def _resolve_request_id(request: Request) -> str:
    """เดียวกับ resolve_request_id() ใน routes/generate.py:
    header > body.request_id > state (ตั้งโดย middleware) > uuid ใหม่

    เดิมฟังก์ชันนี้ (ตอนนั้นชื่อ _request_id) เช็คแค่ header > uuid ใหม่ ข้าม
    body.request_id ไปเลย ทำให้ error response ได้ request_id คนละตัวกับตอน
    success (ที่ resolve_request_id() เลือก body.request_id เมื่อไม่มี header)
    หากไคลเอนต์ส่ง request_id มาทาง body อย่างเดียวโดยไม่ส่ง header
    """
    header_rid = request.headers.get("X-Request-ID")
    if header_rid:
        return header_rid
    try:
        # request.body() ถูก cache ไว้ใน Starlette หลังอ่านครั้งแรก (ตอน validate
        # body ปกติของ route) เรียกซ้ำที่นี่จึงไม่ทำให้ stream เสีย
        body = await request.json()
        if isinstance(body, dict):
            body_rid = sanitize_request_id(body.get("request_id"))
            if body_rid:
                return body_rid
    except Exception:  # noqa: BLE001, S110
        pass
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


async def problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
) -> JSONResponse:
    rid = await _resolve_request_id(request)
    body = {
        "type": f"{PROBLEM_BASE}/{code.lower().replace('_', '-')}",
        "title": title,
        "status": status_code,
        "code": code,
        "detail": detail,
        "service": "generation",
        "request_id": rid,
    }
    resp = JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",
    )
    resp.headers["X-Request-ID"] = rid
    return resp


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return await problem_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail="คำขอไม่ถูกต้องตามรูปแบบที่กำหนด",
        )

    @app.exception_handler(AppValidationError)
    async def app_validation_handler(request: Request, exc: AppValidationError):
        return await problem_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            title="Validation error",
            detail=exc.detail,
        )

    @app.exception_handler(LLMUnavailable)
    async def llm_unavailable_handler(request: Request, exc: LLMUnavailable):
        return await problem_response(
            request,
            status_code=503,
            code="LLM_UNAVAILABLE",
            title="LLM unavailable",
            detail=str(exc) or "ผู้ให้บริการ LLM ทั้งหมดไม่พร้อมใช้งานในขณะนี้",
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        return await problem_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            title="Internal error",
            detail="เกิดข้อผิดพลาดภายในระบบ",
        )
