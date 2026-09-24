"""Keyed hashing for pseudonyms and IP addresses (docs/03_data_design.md section 7)."""

from __future__ import annotations

import hashlib
import hmac

from pydantic import SecretStr

# Used only in dev/test when no secret is configured; production requires real
# secrets (see Settings._production_guards).
_DEV_FALLBACK = b"dev-only-not-a-secret"


def keyed_hash(secret: SecretStr | None, value: str) -> str:
    key = secret.get_secret_value().encode() if secret is not None else _DEV_FALLBACK
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
