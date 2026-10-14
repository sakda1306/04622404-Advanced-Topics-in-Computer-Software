"""Problem-JSON error bodies (CONTRACT.md §0)."""

from __future__ import annotations

import json
from typing import Any

from fastapi.responses import JSONResponse

from app.core.errors import ERROR_SPECS, AppError, ErrorCode, FieldError
from app.core.ids import request_id_var

PROBLEM_MEDIA_TYPE = "application/problem+json"
SERVICE_NAME = "api"


class ProblemResponse(JSONResponse):
    media_type = PROBLEM_MEDIA_TYPE

    def render(self, content: Any) -> bytes:
        # Thai text goes out as UTF-8, not as \u escapes.
        return json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()


def problem_body(
    code: ErrorCode,
    *,
    type_base_url: str,
    detail: str | None = None,
    errors: list[FieldError] | None = None,
) -> dict[str, Any]:
    spec = ERROR_SPECS[code]
    body: dict[str, Any] = {
        "type": f"{type_base_url.rstrip('/')}/{code.value.lower().replace('_', '-')}",
        "title": spec.title,
        "status": spec.status,
        "code": code.value,
        "detail": detail or spec.detail,
        "service": SERVICE_NAME,
        "request_id": request_id_var.get(),
    }
    if errors:
        body["errors"] = [{"field": e.field, "message": e.message, "code": e.code} for e in errors]
    return body


def problem_response(
    code: ErrorCode,
    *,
    type_base_url: str,
    detail: str | None = None,
    errors: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = problem_body(code, type_base_url=type_base_url, detail=detail, errors=errors)
    return ProblemResponse(body, status_code=body["status"], headers=headers)


def app_error_response(exc: AppError, *, type_base_url: str) -> JSONResponse:
    headers = dict(exc.headers)
    if exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return problem_response(
        exc.code,
        type_base_url=type_base_url,
        detail=exc.detail,
        errors=exc.errors,
        headers=headers or None,
    )
