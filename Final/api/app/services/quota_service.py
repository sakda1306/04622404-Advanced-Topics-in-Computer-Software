"""Per-user daily quota (PRD FR-23, FR-24; Design.md §4.7).

Use around every LLM call:

    day = await reserve(db, user_id, settings, estimated_tokens=...)  # before the call
    await add_tokens(db, user_id, day, tokens_used)  # after it succeeds
    await refund(db, user_id, day)  # on LLM_UNAVAILABLE or LLM_TIMEOUT

`reserve` returns the quota day, so a call that ends after midnight is still counted on
the day it started.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import iso, utcnow
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.infra.models import QuotaUsage


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    day: date
    requests_used: int
    requests_limit: int
    tokens_used: int
    tokens_limit: int
    reset_at: datetime

    @property
    def requests_remaining(self) -> int:
        return max(self.requests_limit - self.requests_used, 0)

    @property
    def tokens_remaining(self) -> int:
        return max(self.tokens_limit - self.tokens_used, 0)

    @property
    def exhausted(self) -> bool:
        return self.requests_remaining == 0 or self.tokens_remaining == 0


def quota_day(now: datetime, tz: str) -> date:
    return now.astimezone(ZoneInfo(tz)).date()


def reset_at(now: datetime, tz: str) -> datetime:
    """Next midnight in the quota time zone."""
    zone = ZoneInfo(tz)
    return datetime.combine(quota_day(now, tz) + timedelta(days=1), time(), tzinfo=zone)


async def get_quota(
    db: AsyncSession, user_id: str, settings: Settings, *, now: datetime | None = None
) -> QuotaStatus:
    now = now or utcnow()
    day = quota_day(now, settings.quota_tz)
    row = await db.get(QuotaUsage, (user_id, day), populate_existing=True)
    return QuotaStatus(
        day=day,
        requests_used=row.requests if row else 0,
        requests_limit=settings.quota_daily_requests,
        tokens_used=row.tokens if row else 0,
        tokens_limit=settings.quota_daily_tokens,
        reset_at=reset_at(now, settings.quota_tz),
    )


async def _ensure_row(db: AsyncSession, user_id: str, day: date) -> None:
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    await db.execute(
        insert(QuotaUsage)
        .values(user_id=user_id, day=day, requests=0, tokens=0)
        .on_conflict_do_nothing()
    )


async def reserve(
    db: AsyncSession,
    user_id: str,
    settings: Settings,
    *,
    estimated_tokens: int = 0,
    now: datetime | None = None,
) -> date:
    """Count one request before an LLM call, or raise QUOTA_EXCEEDED (no LLM call is made).

    The check and the increment are one UPDATE, so parallel calls cannot pass the limit.
    """
    now = now or utcnow()
    day = quota_day(now, settings.quota_tz)
    await _ensure_row(db, user_id, day)
    result = await db.execute(
        update(QuotaUsage)
        .where(
            QuotaUsage.user_id == user_id,
            QuotaUsage.day == day,
            QuotaUsage.requests < settings.quota_daily_requests,
            QuotaUsage.tokens + estimated_tokens <= settings.quota_daily_tokens,
        )
        .values(requests=QuotaUsage.requests + 1)
    )
    await db.commit()
    if result.rowcount == 1:  # type: ignore[attr-defined]
        return day

    used_requests = await db.scalar(
        select(QuotaUsage.requests).where(QuotaUsage.user_id == user_id, QuotaUsage.day == day)
    )
    reason = "requests" if (used_requests or 0) >= settings.quota_daily_requests else "tokens"
    raise AppError(
        ErrorCode.QUOTA_EXCEEDED,
        details={"reset_at": iso(reset_at(now, settings.quota_tz)), "reason": reason},
    )


async def add_tokens(db: AsyncSession, user_id: str, day: date, tokens: int) -> None:
    """Add the tokens an LLM call actually used (Contract: "counts" = one request + tokens)."""
    await db.execute(
        update(QuotaUsage)
        .where(QuotaUsage.user_id == user_id, QuotaUsage.day == day)
        .values(tokens=QuotaUsage.tokens + max(tokens, 0))
    )
    await db.commit()


async def refund(db: AsyncSession, user_id: str, day: date) -> None:
    """Give the request back when the LLM failed (LLM_UNAVAILABLE, LLM_TIMEOUT)."""
    await db.execute(
        update(QuotaUsage)
        .where(QuotaUsage.user_id == user_id, QuotaUsage.day == day, QuotaUsage.requests > 0)
        .values(requests=QuotaUsage.requests - 1)
    )
    await db.commit()
