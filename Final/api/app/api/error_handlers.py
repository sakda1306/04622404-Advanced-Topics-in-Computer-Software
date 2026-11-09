"""Map every exception to a Problem-JSON response without leaking internals."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.problem import app_error_response, problem_response
from app.core.errors import STATUS_TO_CODE, AppError, ErrorCode
from app.core.logging import get_logger

log = get_logger(__name__)

_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


def _field_path(loc: tuple[int | str, ...]) -> str:
    parts = [str(p) for p in loc]
    if parts and parts[0] in _LOC_PREFIXES and len(parts) > 1:
        parts = parts[1:]
    return ".".join(parts)


def validation_fields(exc: RequestValidationError) -> list[dict[str, Any]]:
    # The submitted value is never echoed back (it may be a password).
    return [
        {
            "field": _field_path(tuple(err.get("loc", ()))),
            "message": str(err.get("msg", "invalid value")),
            "code": str(err.get("type", "invalid")),
        }
        for err in exc.errors()
    ]


def register_error_handlers(app: FastAPI, *, type_base_url: str) -> None:
    async def handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, AppError)
        if exc.status >= 500:
            log.warning("app_error", code=exc.code.value, **exc.log_context)
        return app_error_response(exc, type_base_url=type_base_url)

    async def handle_validation(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return problem_response(
            ErrorCode.VALIDATION_ERROR,
            type_base_url=type_base_url,
            details={"fields": validation_fields(exc)},
        )

    async def handle_http(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        status = exc.status_code
        code = STATUS_TO_CODE.get(status)
        if code is None:
            # Keep the original 4xx status; anything else is a server error.
            code = ErrorCode.HTTP_ERROR if 400 <= status < 500 else ErrorCode.INTERNAL_ERROR
            status = status if code is ErrorCode.HTTP_ERROR else 500
        return problem_response(
            code,
            type_base_url=type_base_url,
            headers=dict(exc.headers) if exc.headers else None,
            status=status,
        )

    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation)
    app.add_exception_handler(StarletteHTTPException, handle_http)
    # Other exceptions are answered by UnhandledErrorMiddleware, inside CORS (see main.py).
