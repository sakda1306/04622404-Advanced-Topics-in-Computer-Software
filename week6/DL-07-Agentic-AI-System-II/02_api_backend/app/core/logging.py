"""Structured logging with redaction of tokens, personal data and exact locations."""

from __future__ import annotations

import logging
import sys
import traceback
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

from app.core.telemetry import add_trace_ids

REDACTED = "[redacted]"

# Keys are matched case-insensitively against these fragments.
_SENSITIVE_FRAGMENTS = (
    "authorization",
    "token",
    "password",
    "secret",
    "cookie",
    "api_key",
    "apikey",
    "email",
    "phone",
)
# Exact keys that hold precise locations or free text from users.
_SENSITIVE_KEYS = frozenset(
    {
        "lat",
        "lon",
        "lng",
        "latitude",
        "longitude",
        "coordinates",
        "origin",
        "destination",
        "waypoints",
        "question",
        "content",
        "comment",
        "display_name",
    }
)
_MAX_DEPTH = 6
# Database errors quote bound values and row data (e.g. "Key (x)=(...)") in their text.
_REDACTED_EXCEPTION_MODULES = ("sqlalchemy", "asyncpg", "psycopg")


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return lowered in _SENSITIVE_KEYS or any(frag in lowered for frag in _SENSITIVE_FRAGMENTS)


def _redact(value: Any, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return REDACTED
    if isinstance(value, Mapping):
        return {
            k: REDACTED if isinstance(k, str) and _is_sensitive(k) else _redact(v, depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(item, depth + 1) for item in value]
    return value


def redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key == "event":
            continue
        if _is_sensitive(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _redact(event_dict[key])
    return event_dict


def _exception_of(exc_info: Any) -> BaseException | None:
    if exc_info is True:
        return sys.exc_info()[1]
    if isinstance(exc_info, BaseException):
        return exc_info
    if isinstance(exc_info, tuple) and len(exc_info) == 3:
        value = exc_info[1]
        return value if isinstance(value, BaseException) else None
    return None


def redact_exception_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Keep the traceback of database errors but drop their message."""
    exc = _exception_of(event_dict.get("exc_info"))
    if exc is None or not type(exc).__module__.startswith(_REDACTED_EXCEPTION_MODULES):
        return event_dict
    event_dict.pop("exc_info")
    frames = "".join(traceback.format_tb(exc.__traceback__))
    event_dict["exception"] = (
        f"Traceback (most recent call last):\n{frames}{type(exc).__name__}: {REDACTED}"
    )
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_trace_ids,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_processor,
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            *shared,
            redact_exception_processor,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        # No explicit file: each logger resolves sys.stdout when it is created, so a
        # replaced stream (test capture, reloader) is never written to after it closes.
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    # Route stdlib loggers (uvicorn, libraries) to the same level.
    logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s", force=True)
    # Access logs are emitted by our own middleware without query strings.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
