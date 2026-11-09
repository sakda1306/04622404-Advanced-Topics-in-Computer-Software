"""Password hashing (bcrypt) and access tokens (JWT HS256, Contract.md §1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from anyio import to_thread

from app.core.config import Settings

# bcrypt only reads the first 72 bytes; longer input is rejected rather than truncated.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


# bcrypt takes ~250 ms of CPU; with one worker it must not run on the event loop.
async def hash_password_async(password: str) -> str:
    return await to_thread.run_sync(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    return await to_thread.run_sync(verify_password, password, password_hash)


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode()
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode())
    except ValueError:
        return False


# Compared against when the email does not exist, so both paths cost the same.
DUMMY_HASH = hash_password("not-a-real-password")


def create_access_token(settings: Settings, user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(settings: Settings, token: str) -> str | None:
    """The user id in the token, or None when it is invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError:
        return None
    return str(payload["sub"])
