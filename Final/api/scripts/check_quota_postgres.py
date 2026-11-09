"""CI check: the quota guard on real Postgres (the tests use SQLite).

Needs DATABASE_URL and JWT_SECRET, a migrated database, and the user ci@example.com.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.infra.db import create_engine, create_session_factory
from app.infra.models import User
from app.services import quota_service


async def main() -> None:
    settings = Settings(quota_daily_requests=3, quota_daily_tokens=1000)  # type: ignore[call-arg]
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    async with sessions() as db:
        user_id = await db.scalar(select(User.id).where(User.email == "ci@example.com"))
    assert user_id, "register ci@example.com first"

    async def reserve() -> object:
        async with sessions() as db:
            try:
                return await quota_service.reserve(db, user_id, settings)
            except AppError as exc:
                return exc

    results = await asyncio.gather(*(reserve() for _ in range(8)))
    errors = [r for r in results if isinstance(r, AppError)]
    assert len(results) - len(errors) == 3, results
    assert all(e.code == ErrorCode.QUOTA_EXCEEDED for e in errors)
    async with sessions() as db:
        status = await quota_service.get_quota(db, user_id, settings)
        assert status.requests_used == 3 and status.exhausted
        await quota_service.add_tokens(db, user_id, status.day, 120)
        await quota_service.refund(db, user_id, status.day)
        status = await quota_service.get_quota(db, user_id, settings)
        assert (status.requests_used, status.tokens_used) == (2, 120), status
    await engine.dispose()
    print("quota on Postgres: ok")


if __name__ == "__main__":
    asyncio.run(main())
