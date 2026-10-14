"""Error codes from CONTRACT.md §1 / §1.1 / §7 and the application error type."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    MESSAGE_NOT_READY = "MESSAGE_NOT_READY"
    USERNAME_TAKEN = "USERNAME_TAKEN"
    CANNOT_MODIFY_SELF = "CANNOT_MODIFY_SELF"
    REPORT_NOT_EDITABLE = "REPORT_NOT_EDITABLE"
    REPORT_ALREADY_PUBLISHED = "REPORT_ALREADY_PUBLISHED"
    JOB_ALREADY_RUNNING = "JOB_ALREADY_RUNNING"
    MATCHWEEK_NOT_COMPLETE = "MATCHWEEK_NOT_COMPLETE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    ROUTER_UNAVAILABLE = "ROUTER_UNAVAILABLE"
    FOOTBALL_DATA_UNAVAILABLE = "FOOTBALL_DATA_UNAVAILABLE"
    SIMULATION_UNAVAILABLE = "SIMULATION_UNAVAILABLE"
    RETRIEVAL_UNAVAILABLE = "RETRIEVAL_UNAVAILABLE"
    INDEX_UPDATE_FAILED = "INDEX_UPDATE_FAILED"
    ROUTER_TIMEOUT = "ROUTER_TIMEOUT"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    status: int
    title: str
    detail: str


ERROR_SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.INVALID_REQUEST: ErrorSpec(400, "Invalid request", "รูปแบบคำขอไม่ถูกต้อง"),
    ErrorCode.UNAUTHENTICATED: ErrorSpec(401, "Unauthenticated", "กรุณาเข้าสู่ระบบ"),
    ErrorCode.ACCOUNT_DISABLED: ErrorSpec(401, "Account disabled", "บัญชีนี้ถูกระงับการใช้งาน"),
    ErrorCode.FORBIDDEN: ErrorSpec(403, "Forbidden", "ไม่มีสิทธิ์ทำรายการนี้"),
    ErrorCode.NOT_FOUND: ErrorSpec(404, "Not found", "ไม่พบข้อมูลที่ขอ"),
    ErrorCode.METHOD_NOT_ALLOWED: ErrorSpec(405, "Method not allowed", "ไม่รองรับ method นี้"),
    ErrorCode.MESSAGE_NOT_READY: ErrorSpec(
        409, "Message not ready", "คำตอบนี้ยังบันทึกไม่เสร็จ ลองใหม่อีกครั้ง"
    ),
    ErrorCode.USERNAME_TAKEN: ErrorSpec(409, "Username taken", "ชื่อผู้ใช้นี้ถูกใช้แล้ว"),
    ErrorCode.CANNOT_MODIFY_SELF: ErrorSpec(
        409, "Cannot modify self", "แก้ role หรือระงับบัญชีของตัวเองไม่ได้"
    ),
    ErrorCode.REPORT_NOT_EDITABLE: ErrorSpec(
        409, "Report not editable", "รายงานที่เผยแพร่อยู่แก้ไม่ได้ ต้อง unpublish ก่อน"
    ),
    ErrorCode.REPORT_ALREADY_PUBLISHED: ErrorSpec(
        409, "Report already published", "รายงานของแมตช์วีคนี้เผยแพร่อยู่แล้ว"
    ),
    ErrorCode.JOB_ALREADY_RUNNING: ErrorSpec(409, "Job already running", "มีงานชนิดเดียวกันกำลังรันอยู่"),
    ErrorCode.MATCHWEEK_NOT_COMPLETE: ErrorSpec(409, "Matchweek not complete", "แมตช์วีคนี้ยังแข่งไม่ครบ"),
    ErrorCode.PAYLOAD_TOO_LARGE: ErrorSpec(413, "Payload too large", "ข้อมูลที่ส่งมาใหญ่เกินไป"),
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: ErrorSpec(
        415, "Unsupported media type", "ส่งข้อมูลเป็น application/json เท่านั้น"
    ),
    ErrorCode.VALIDATION_ERROR: ErrorSpec(422, "Validation error", "ข้อมูลบางช่องไม่ถูกต้อง"),
    ErrorCode.RATE_LIMITED: ErrorSpec(429, "Too many requests", "ส่งคำขอถี่เกินไป รอสักครู่"),
    ErrorCode.QUOTA_EXHAUSTED: ErrorSpec(429, "Quota exhausted", "โควตา API-Football ของวันนี้หมดแล้ว"),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(500, "Internal error", "เกิดข้อผิดพลาดภายในระบบ"),
    ErrorCode.ROUTER_UNAVAILABLE: ErrorSpec(
        502, "Router unavailable", "ระบบตอบคำถามไม่พร้อมใช้งานชั่วคราว"
    ),
    ErrorCode.FOOTBALL_DATA_UNAVAILABLE: ErrorSpec(
        502, "Football data unavailable", "บริการข้อมูลฟุตบอลไม่พร้อมใช้งานชั่วคราว"
    ),
    ErrorCode.SIMULATION_UNAVAILABLE: ErrorSpec(
        503, "Simulation unavailable", "ระบบทำนายผลไม่พร้อมใช้งานตอนนี้"
    ),
    ErrorCode.RETRIEVAL_UNAVAILABLE: ErrorSpec(
        502, "Retrieval unavailable", "บริการคลังความรู้ไม่พร้อมใช้งานชั่วคราว"
    ),
    ErrorCode.INDEX_UPDATE_FAILED: ErrorSpec(
        502, "Index update failed", "อัปเดตคลังความรู้ไม่สำเร็จ สถานะรายงานไม่เปลี่ยน"
    ),
    ErrorCode.ROUTER_TIMEOUT: ErrorSpec(504, "Router timed out", "ระบบตอบคำถามใช้เวลานานเกินไป"),
}

STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
}


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    message: str
    code: str


@dataclass(eq=False)
class AppError(Exception):
    """Raised by any layer; the API layer turns it into a Problem-JSON response.

    `detail` must be safe to show to users: no stack traces, SQL, hosts or secrets.
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
