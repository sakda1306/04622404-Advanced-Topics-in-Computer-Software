"""Map every exception to a Problem Details response without leaking internals."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.problem import app_error_response, problem_response
from app.core.errors import STATUS_TO_CODE, AppError, ErrorCode, FieldError
from app.core.logging import get_logger
from app.domain.errors import InvalidInput

log = get_logger(__name__)

# Locations FastAPI prefixes to field paths; they add noise for clients.
_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


def _field_path(loc: tuple[int | str, ...]) -> str:
    parts = [str(p) for p in loc]
    if parts and parts[0] in _LOC_PREFIXES and len(parts) > 1:
        parts = parts[1:]
    return ".".join(parts)


def validation_field_errors(exc: RequestValidationError) -> list[FieldError]:
    # The submitted value ("input") is never echoed back; it may hold personal data.
    return [
        FieldError(
            field=_field_path(tuple(err.get("loc", ()))),
            message=str(err.get("msg", "invalid value")),
            code=str(err.get("type", "invalid")),
        )
        for err in exc.errors()
    ]


def register_error_handlers(app: FastAPI, *, type_base_url: str) -> None:
    async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, AppError)
        if exc.status >= 500:
            log.warning("app_error", code=exc.code.value, **exc.log_context)
        return app_error_response(exc, instance=request.url.path, type_base_url=type_base_url)

    async def handle_validation(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return problem_response(
            ErrorCode.VALIDATION_ERROR,
            instance=request.url.path,
            type_base_url=type_base_url,
            errors=validation_field_errors(exc),
        )

    async def handle_invalid_input(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, InvalidInput)
        return problem_response(
            ErrorCode.VALIDATION_ERROR,
            instance=request.url.path,
            type_base_url=type_base_url,
            errors=[FieldError(field=i.field, message=i.message, code=i.code) for i in exc.issues],
        )

    async def handle_http(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        code = STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return problem_response(
            code,
            instance=request.url.path,
            type_base_url=type_base_url,
            headers=dict(exc.headers) if exc.headers else None,
        )

    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", error_type=type(exc).__name__)
        return problem_response(
            ErrorCode.INTERNAL_ERROR, instance=request.url.path, type_base_url=type_base_url
        )

    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation)
    app.add_exception_handler(InvalidInput, handle_invalid_input)
    app.add_exception_handler(StarletteHTTPException, handle_http)
    app.add_exception_handler(Exception, handle_unexpected)
