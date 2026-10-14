"""Per-key fixed-window rate limits.

- /api/chat: 20 calls per minute per user (CONTRACT §1)
- login: failed attempts per username; successful logins are not counted, because every
  user reaches the api through the web proxy and so shares one client IP
"""

from __future__ import annotations

from app.core.errors import AppError, ErrorCode
from app.infra.store import Store

WINDOW_SECONDS = 60


async def enforce_rate_limit(store: Store, bucket: str, key: str, limit_per_minute: int) -> None:
    count, reset_in = await store.hit(f"rl:{bucket}:{key}", WINDOW_SECONDS)
    if count > limit_per_minute:
        raise AppError(ErrorCode.RATE_LIMITED, retry_after=reset_in)


async def enforce_failure_limit(store: Store, bucket: str, key: str, limit_per_minute: int) -> None:
    """Refuse once `limit_per_minute` failures were recorded for the key in this window."""
    failures = await store.get_json(f"rl:{bucket}:{key}")
    if isinstance(failures, int) and failures >= limit_per_minute:
        raise AppError(ErrorCode.RATE_LIMITED, retry_after=WINDOW_SECONDS)


async def record_failure(store: Store, bucket: str, key: str) -> None:
    await store.hit(f"rl:{bucket}:{key}", WINDOW_SECONDS)
