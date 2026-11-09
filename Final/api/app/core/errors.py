"""Error codes from Contract.md §4 and the application error type."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    EMAIL_TAKEN = "EMAIL_TAKEN"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    CV_INVALID_TYPE = "CV_INVALID_TYPE"
    CV_TOO_LARGE = "CV_TOO_LARGE"
    CV_UNREADABLE = "CV_UNREADABLE"
    QUESTION_NOT_FOUND = "QUESTION_NOT_FOUND"
    PROFILE_NOT_READY = "PROFILE_NOT_READY"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    EDIT_NOT_FOUND = "EDIT_NOT_FOUND"
    EDIT_EXPIRED = "EDIT_EXPIRED"
    EDIT_CONFLICT = "EDIT_CONFLICT"
    EDIT_FIELD_NOT_ALLOWED = "EDIT_FIELD_NOT_ALLOWED"
    SKILL_NOT_FOUND = "SKILL_NOT_FOUND"
    ROLE_NOT_FOUND = "ROLE_NOT_FOUND"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # Generic HTTP errors raised outside our own code (proposed for Contract v0.2).
    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    # Any other 4xx; the response keeps the original status.
    HTTP_ERROR = "HTTP_ERROR"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    status: int
    title: str
    message_th: str


ERROR_SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.VALIDATION_ERROR: ErrorSpec(
        422, "Validation error", "ข้อมูลบางช่องไม่ถูกต้อง กรุณาตรวจสอบแล้วลองใหม่"
    ),
    ErrorCode.UNAUTHENTICATED: ErrorSpec(401, "Unauthenticated", "กรุณาเข้าสู่ระบบ"),
    ErrorCode.INVALID_CREDENTIALS: ErrorSpec(401, "Invalid credentials", "อีเมลหรือรหัสผ่านไม่ถูกต้อง"),
    ErrorCode.EMAIL_TAKEN: ErrorSpec(409, "Email taken", "อีเมลนี้มีบัญชีอยู่แล้ว กรุณาเข้าสู่ระบบ"),
    ErrorCode.RATE_LIMITED: ErrorSpec(429, "Too many requests", "ส่งคำขอถี่เกินไป กรุณารอสักครู่แล้วลองใหม่"),
    ErrorCode.QUOTA_EXCEEDED: ErrorSpec(
        429,
        "Daily quota exceeded",
        "วันนี้คุณใช้โควตาถาม AI ครบแล้ว ระบบจะรีเซ็ตเวลา 00:00 น. "
        "ระหว่างนี้ยังลบทักษะหรือแก้ข้อมูลในโปรไฟล์ได้ตามปกติ",
    ),
    ErrorCode.CV_INVALID_TYPE: ErrorSpec(
        415, "CV is not a PDF", "ไฟล์นี้ไม่ใช่ PDF กรุณาอัปโหลดไฟล์ .pdf ขนาดไม่เกิน 5 MB"
    ),
    ErrorCode.CV_TOO_LARGE: ErrorSpec(413, "CV too large", "ไฟล์ใหญ่เกิน 5 MB กรุณาลดขนาดไฟล์แล้วลองใหม่"),
    ErrorCode.CV_UNREADABLE: ErrorSpec(
        422,
        "CV unreadable",
        "อ่านข้อความจาก PDF นี้ไม่ได้ (อาจเป็นไฟล์สแกน) กรุณาใช้ PDF ที่คัดลอกข้อความได้ หรือข้ามไปทำแบบสอบถามแทน",
    ),
    ErrorCode.QUESTION_NOT_FOUND: ErrorSpec(404, "Question not found", "ไม่พบคำถามข้อนี้"),
    ErrorCode.PROFILE_NOT_READY: ErrorSpec(
        409, "Profile not ready", "ข้อมูลยังไม่พอสำหรับสร้างโปรไฟล์ กรุณาตอบเพิ่มอีกเล็กน้อย"
    ),
    ErrorCode.PROFILE_NOT_FOUND: ErrorSpec(
        404, "Profile not found", "ยังไม่มีโปรไฟล์ กรุณาสร้างโปรไฟล์ก่อน"
    ),
    ErrorCode.EDIT_NOT_FOUND: ErrorSpec(404, "Edit not found", "ไม่พบรายการแก้ไขนี้"),
    ErrorCode.EDIT_EXPIRED: ErrorSpec(
        409, "Edit expired", "รายการแก้ไขนี้หมดอายุแล้ว กรุณาขอแก้ไขใหม่อีกครั้ง"
    ),
    ErrorCode.EDIT_CONFLICT: ErrorSpec(
        409, "Edit conflict", "ข้อมูลถูกเปลี่ยนไปแล้วหลังจากเสนอการแก้ไข กรุณาขอแก้ไขใหม่"
    ),
    ErrorCode.EDIT_FIELD_NOT_ALLOWED: ErrorSpec(
        422, "Edit field not allowed", "แก้ไขข้อมูลส่วนนี้ผ่านแชทไม่ได้"
    ),
    ErrorCode.SKILL_NOT_FOUND: ErrorSpec(404, "Skill not found", "ไม่พบทักษะนี้ในโปรไฟล์"),
    ErrorCode.ROLE_NOT_FOUND: ErrorSpec(404, "Role not found", "ไม่พบสายงานนี้"),
    ErrorCode.LLM_UNAVAILABLE: ErrorSpec(
        503, "AI unavailable", "AI ไม่พร้อมใช้งานชั่วคราว กรุณาลองใหม่อีกครั้ง ระบบไม่นับคำขอนี้"
    ),
    ErrorCode.LLM_TIMEOUT: ErrorSpec(
        504, "AI timed out", "AI ใช้เวลานานเกินไป กรุณาลองใหม่อีกครั้ง ระบบไม่นับคำขอนี้"
    ),
    ErrorCode.FORBIDDEN: ErrorSpec(403, "Forbidden", "บัญชีนี้ไม่มีสิทธิ์เข้าถึงส่วนนี้"),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(500, "Internal error", "เกิดข้อผิดพลาดในระบบ กรุณาลองใหม่อีกครั้ง"),
    ErrorCode.BAD_REQUEST: ErrorSpec(400, "Bad request", "รูปแบบคำขอไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง"),
    ErrorCode.NOT_FOUND: ErrorSpec(404, "Not found", "ไม่พบข้อมูลที่ขอ"),
    ErrorCode.METHOD_NOT_ALLOWED: ErrorSpec(405, "Method not allowed", "ไม่รองรับคำขอแบบนี้"),
    ErrorCode.PAYLOAD_TOO_LARGE: ErrorSpec(413, "Payload too large", "ข้อมูลที่ส่งมาใหญ่เกินไป"),
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: ErrorSpec(
        415, "Unsupported media type", "รูปแบบข้อมูลไม่ถูกต้อง กรุณาส่งเป็น JSON"
    ),
    # 400 is a placeholder: the response carries the status of the original error.
    ErrorCode.HTTP_ERROR: ErrorSpec(400, "Request error", "ทำรายการนี้ไม่ได้ กรุณาลองใหม่อีกครั้ง"),
}

STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


@dataclass(eq=False)
class AppError(Exception):
    """Raised by any layer; the API layer turns it into a Problem-JSON response.

    `message_th` overrides the default text and must be safe to show to users.
    """

    code: ErrorCode
    message_th: str | None = None
    details: dict[str, Any] | None = None
    retry_after: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    log_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.code.value)

    @property
    def spec(self) -> ErrorSpec:
        return ERROR_SPECS[self.code]

    @property
    def status(self) -> int:
        return self.spec.status
