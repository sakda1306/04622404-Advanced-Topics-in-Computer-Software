"""Column encryption for free text users write (D-15, D-81).

Values are AES-256-GCM encrypted by the application before they reach PostgreSQL:
`enc:v1:<key id>:<base64(nonce + ciphertext)>`. The column name is the associated data,
so a value copied into another column does not decrypt. Old keys stay in the key list
for reading; new values always use the active key (key rotation). Values without the
prefix are plaintext written before encryption was enabled and are returned as they are.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

PREFIX = "enc:v1:"
KEY_BYTES = 32
_NONCE_BYTES = 12
# Used only in dev/test when no key is configured; production requires real keys
# (see Settings._production_guards).
DEV_KEY_ID = "dev"
_DEV_KEY = hashlib.sha256(b"dev-only-column-key-not-a-secret").digest()


class EncryptionError(Exception):
    """A value could not be decrypted (unknown key, wrong column or tampered data)."""


def parse_keys(raw: str) -> dict[str, bytes]:
    """`kid1:base64key,kid0:base64key` -> {kid: key}; the first entry is the active key."""
    keys: dict[str, bytes] = {}
    for part in raw.split(","):
        kid, sep, encoded = part.strip().partition(":")
        if not sep or not kid or not kid.isalnum():
            raise ValueError("use key-id:base64-key pairs separated by commas")
        try:
            key = base64.b64decode(encoded, validate=True)
        except binascii.Error as exc:
            raise ValueError(f"key {kid!r} is not valid base64") from exc
        if len(key) != KEY_BYTES:
            raise ValueError(f"key {kid!r} must be {KEY_BYTES} bytes")
        if kid in keys:
            raise ValueError(f"key id {kid!r} is listed twice")
        keys[kid] = key
    return keys


class ColumnCipher:
    def __init__(self, keys: dict[str, bytes], active: str) -> None:
        if active not in keys:
            raise ValueError("the active key must be in the key list")
        self._keys = {kid: AESGCM(key) for kid, key in keys.items()}
        self._active = active

    @classmethod
    def from_secret(cls, secret: SecretStr | None) -> ColumnCipher:
        if secret is None:
            return cls({DEV_KEY_ID: _DEV_KEY}, DEV_KEY_ID)
        keys = parse_keys(secret.get_secret_value())
        return cls(keys, next(iter(keys)))

    @staticmethod
    def is_encrypted(value: str) -> bool:
        return value.startswith(PREFIX)

    def encrypt(self, plaintext: str, *, column: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        sealed = self._keys[self._active].encrypt(nonce, plaintext.encode(), column.encode())
        return f"{PREFIX}{self._active}:{base64.b64encode(nonce + sealed).decode()}"

    def decrypt(self, value: str, *, column: str) -> str:
        if not self.is_encrypted(value):
            return value
        kid, _, encoded = value[len(PREFIX) :].partition(":")
        cipher = self._keys.get(kid)
        if cipher is None:
            raise EncryptionError(f"unknown key id {kid!r}")
        try:
            raw = base64.b64decode(encoded, validate=True)
            return cipher.decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], column.encode()).decode()
        except (binascii.Error, InvalidTag, ValueError) as exc:
            raise EncryptionError("the value cannot be decrypted") from exc


@lru_cache
def column_cipher() -> ColumnCipher:
    """The process-wide cipher, built from COLUMN_ENCRYPTION_KEYS on first use."""
    from app.core.config import SecretSettings

    return ColumnCipher.from_secret(SecretSettings().column_encryption_keys)
