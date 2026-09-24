"""Output hygiene for text and links that reach users (rule R-06)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit, urlunsplit

# C0/C1 controls except tab and newline, plus zero-width and bidi override characters
# that can hide or reorder text.
_UNSAFE_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]")
_ELLIPSIS = "…"

INTERNAL_KEYS = frozenset(
    {"diagnostics", "prompt", "prompts", "tool_trace", "trace", "cost", "debug", "internal"}
)


def clean_text(value: str | None) -> str | None:
    """Normalize to NFC, unify newlines, drop unsafe characters. Blank -> None."""
    if value is None:
        return None
    text = unicodedata.normalize("NFC", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _UNSAFE_CHARS.sub("", text).strip()
    return text or None


def truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 1] + _ELLIPSIS


def safe_url(value: str | None, *, max_length: int = 2048) -> str | None:
    """Return the URL only if it is an https link without embedded credentials."""
    if not value:
        return None
    candidate = value.strip()
    if len(candidate) > max_length:
        return None
    try:
        # Malformed hosts (e.g. "[::1") and ports raise ValueError when parsed.
        parts = urlsplit(candidate)
        hostname, _port = parts.hostname, parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or not hostname or any(c.isspace() for c in hostname):
        return None
    if parts.username is not None or parts.password is not None:
        return None
    return urlunsplit(parts)


def _is_internal(key: str) -> bool:
    return key in INTERNAL_KEYS or key.startswith(("_", "internal_"))


def strip_internal(data: Any) -> Any:
    """Copy of `data` without fields that must never reach users."""
    if isinstance(data, dict):
        return {k: strip_internal(v) for k, v in data.items() if not _is_internal(str(k))}
    if isinstance(data, list):
        return [strip_internal(item) for item in data]
    return data
