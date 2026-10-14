"""Error codes for 05 (CONTRACT §0, §4, §6) and the application error type."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    JOB_ALREADY_RUNNING = "JOB_ALREADY_RUNNING"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INDEX_NOT_READY = "INDEX_NOT_READY"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    status: int
    title: str
    detail: str


ERROR_SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.INVALID_REQUEST: ErrorSpec(400, "Invalid request", "รูปแบบคำขอไม่ถูกต้อง"),
    ErrorCode.NOT_FOUND: ErrorSpec(404, "Not found", "ไม่พบข้อมูลที่ขอ"),
    ErrorCode.METHOD_NOT_ALLOWED: ErrorSpec(405, "Method not allowed", "ไม่รองรับ method นี้"),
    ErrorCode.JOB_ALREADY_RUNNING: ErrorSpec(409, "Job already running", "มีงานชนิดเดียวกันกำลังรันอยู่"),
    ErrorCode.PAYLOAD_TOO_LARGE: ErrorSpec(413, "Payload too large", "ข้อมูลที่ส่งมาใหญ่เกินไป"),
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: ErrorSpec(
        415, "Unsupported media type", "ส่งข้อมูลเป็น application/json เท่านั้น"
    ),
    ErrorCode.VALIDATION_ERROR: ErrorSpec(422, "Validation error", "ข้อมูลบางช่องไม่ถูกต้อง"),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(500, "Internal error", "เกิดข้อผิดพลาดภายในระบบ"),
    ErrorCode.INDEX_NOT_READY: ErrorSpec(
        503, "Index not ready", "คลังความรู้ยังโหลดไม่เสร็จ ลองใหม่อีกครั้ง"
    ),
}

STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_REQUEST,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
}


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    message: str
    code: str


@dataclass(eq=False)
class AppError(Exception):
    """Raised by any layer; the API layer turns it into a Problem-JSON response.

    `detail` must be safe to show to callers: no stack traces, SQL, paths or secrets.
    """

    code: ErrorCode
    detail: str | None = None
    errors: list[FieldError] | None = None
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
