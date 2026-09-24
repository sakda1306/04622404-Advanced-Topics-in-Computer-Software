"""Stable error codes and the application error type (docs/02_api_spec.md section 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    IDEMPOTENCY_IN_PROGRESS = "IDEMPOTENCY_IN_PROGRESS"
    JOB_NOT_CANCELLABLE = "JOB_NOT_CANCELLABLE"
    REVIEW_NOT_PENDING = "REVIEW_NOT_PENDING"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNSUPPORTED_REGION = "UNSUPPORTED_REGION"
    RATE_LIMITED = "RATE_LIMITED"
    TOO_MANY_ACTIVE_JOBS = "TOO_MANY_ACTIVE_JOBS"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    AGENT_BAD_RESPONSE = "AGENT_BAD_RESPONSE"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    status: int
    title: str
    detail: str


ERROR_SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.INVALID_REQUEST: ErrorSpec(400, "Invalid request", "The request is malformed."),
    ErrorCode.UNAUTHENTICATED: ErrorSpec(
        401, "Unauthenticated", "A valid access token is required."
    ),
    ErrorCode.FORBIDDEN: ErrorSpec(
        403, "Forbidden", "You do not have permission to perform this action."
    ),
    ErrorCode.NOT_FOUND: ErrorSpec(404, "Not found", "The requested resource was not found."),
    ErrorCode.METHOD_NOT_ALLOWED: ErrorSpec(
        405, "Method not allowed", "This method is not supported for the resource."
    ),
    ErrorCode.IDEMPOTENCY_CONFLICT: ErrorSpec(
        409, "Idempotency conflict", "This Idempotency-Key was used with a different request."
    ),
    ErrorCode.IDEMPOTENCY_IN_PROGRESS: ErrorSpec(
        409, "Request in progress", "A request with this Idempotency-Key is still running."
    ),
    ErrorCode.JOB_NOT_CANCELLABLE: ErrorSpec(
        409, "Job not cancellable", "The job has already finished."
    ),
    ErrorCode.REVIEW_NOT_PENDING: ErrorSpec(
        409, "Review not pending", "This feedback has already been reviewed."
    ),
    ErrorCode.PAYLOAD_TOO_LARGE: ErrorSpec(
        413, "Payload too large", "The request body is too large."
    ),
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: ErrorSpec(
        415, "Unsupported media type", "Send the request body as application/json."
    ),
    ErrorCode.VALIDATION_ERROR: ErrorSpec(
        422, "Validation error", "One or more fields are invalid."
    ),
    ErrorCode.UNSUPPORTED_REGION: ErrorSpec(
        422, "Unsupported region", "The location is outside the service area."
    ),
    ErrorCode.RATE_LIMITED: ErrorSpec(
        429, "Too many requests", "Rate limit reached. Try again later."
    ),
    ErrorCode.TOO_MANY_ACTIVE_JOBS: ErrorSpec(
        429, "Too many active jobs", "Wait for your running requests to finish."
    ),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(500, "Internal error", "An unexpected error occurred."),
    ErrorCode.AGENT_BAD_RESPONSE: ErrorSpec(
        502, "Bad upstream response", "The advisory service returned an invalid result."
    ),
    ErrorCode.DEPENDENCY_UNAVAILABLE: ErrorSpec(
        503, "Service unavailable", "A required service is temporarily unavailable."
    ),
    ErrorCode.AGENT_TIMEOUT: ErrorSpec(
        504, "Upstream timeout", "The advisory service did not respond in time."
    ),
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
    503: ErrorCode.DEPENDENCY_UNAVAILABLE,
    504: ErrorCode.AGENT_TIMEOUT,
}


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    message: str
    code: str


@dataclass(eq=False)
class AppError(Exception):
    """Raised by any layer; the API layer turns it into a Problem Details response.

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
