"""Password hashing (bcrypt) and access tokens (JWT HS256, CONTRACT.md §1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from app.core.config import Settings

# bcrypt only reads the first 72 bytes; longer input is rejected rather than truncated.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode()
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode())
    except ValueError:
        return False


# Compared against when the username does not exist, so both paths cost the same.
DUMMY_HASH = hash_password("not-a-real-password")


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: UUID
    role: str


def create_access_token(settings: Settings, user_id: UUID, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(settings: Settings, token: str) -> TokenClaims | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        return TokenClaims(user_id=UUID(str(payload["sub"])), role=str(payload.get("role", "")))
    except (jwt.PyJWTError, ValueError):
        return None
