"""JSON logs, one line per event, with the request id and secrets redacted."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[redacted]"

_SENSITIVE_FRAGMENTS = ("authorization", "token", "password", "secret", "cookie", "api_key")
# Free text typed by users stays out of the logs; it lives in the database only.
_SENSITIVE_KEYS = frozenset({"message", "query", "content", "comment", "answer"})
_MAX_DEPTH = 6


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
        event_dict[key] = REDACTED if _is_sensitive(key) else _redact(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", json_output: bool = True, service: str = "api") -> None:
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_processor,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    structlog.contextvars.bind_contextvars(service=service)
    logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s", force=True)
    # Access logs come from our own middleware, without query strings.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
