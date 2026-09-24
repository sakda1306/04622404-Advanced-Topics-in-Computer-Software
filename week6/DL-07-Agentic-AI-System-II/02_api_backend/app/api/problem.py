"""RFC 9457 Problem Details responses."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from app.core.errors import ERROR_SPECS, AppError, ErrorCode, FieldError
from app.core.ids import current_correlation_id, current_request_id

PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem_body(
    code: ErrorCode,
    *,
    instance: str,
    type_base_url: str,
    detail: str | None = None,
    errors: list[FieldError] | None = None,
) -> dict[str, Any]:
    spec = ERROR_SPECS[code]
    return {
        "type": f"{type_base_url.rstrip('/')}/{code.value.lower().replace('_', '-')}",
        "title": spec.title,
        "status": spec.status,
        "code": code.value,
        "detail": detail or spec.detail,
        "instance": instance,
        "request_id": current_request_id(),
        "correlation_id": current_correlation_id(),
        "errors": (
            [{"field": e.field, "message": e.message, "code": e.code} for e in errors]
            if errors
            else None
        ),
    }


def problem_response(
    code: ErrorCode,
    *,
    instance: str,
    type_base_url: str,
    detail: str | None = None,
    errors: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = problem_body(
        code, instance=instance, type_base_url=type_base_url, detail=detail, errors=errors
    )
    return JSONResponse(
        body, status_code=body["status"], headers=headers, media_type=PROBLEM_MEDIA_TYPE
    )


def app_error_response(exc: AppError, *, instance: str, type_base_url: str) -> JSONResponse:
    headers = dict(exc.headers)
    if exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return problem_response(
        exc.code,
        instance=instance,
        type_base_url=type_base_url,
        detail=exc.detail,
        errors=exc.errors,
        headers=headers or None,
    )
