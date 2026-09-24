"""Signing keys and token builders for tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

ALL_USER_SCOPES = ("travel:read", "travel:write", "profile:read", "profile:write")


def generate_signing_key(kid: str = "test-key") -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": kid, "alg": "RS256", "use": "sig"})


def public_key_set(*keys: RSAKey) -> KeySet:
    return KeySet([RSAKey.import_key(key.as_dict(private=False)) for key in keys])


def jwks_document(*keys: RSAKey) -> dict[str, Any]:
    return {"keys": [key.as_dict(private=False) for key in keys]}


@dataclass
class TokenFactory:
    key: RSAKey
    issuer: str
    audience: str

    def __call__(
        self,
        subject: str = "user-1",
        scopes: Iterable[str] = ALL_USER_SCOPES,
        *,
        lifetime: timedelta = timedelta(minutes=15),
        now: datetime | None = None,
        header: dict[str, Any] | None = None,
        key: RSAKey | None = None,
        **claims: Any,
    ) -> str:
        issued = now or datetime.now(UTC)
        signer = key or self.key
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": subject,
            "scope": " ".join(scopes),
            "iat": int(issued.timestamp()),
            "exp": int((issued + lifetime).timestamp()),
            **claims,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        protected = {"alg": "RS256", "kid": signer.kid, **(header or {})}
        return jwt.encode(protected, payload, signer)
