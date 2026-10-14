"""Seed accounts (CONTRACT §1.1): `admin` + `demo1`–`demo3`. Safe to run again.

    python -m app.seed

Passwords come from SEED_ADMIN_PASSWORD / SEED_DEMO_PASSWORD; an empty one skips
those accounts.
Existing accounts are left as they are (passwords are not reset).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.models import User
from app.db.session import create_engine, create_session_factory

log = get_logger(__name__)

DEMO_USERS = (("demo1", "Demo 1"), ("demo2", "Demo 2"), ("demo3", "Demo 3"))


async def seed_users(db: AsyncSession, settings: Settings) -> list[str]:
    wanted: list[tuple[str, str, str, str]] = []
    if settings.seed_admin_password:
        wanted.append(("admin", "Admin", "admin", settings.seed_admin_password))
    else:
        log.warning("seed_admin_skipped", reason="SEED_ADMIN_PASSWORD is empty")
    if settings.seed_demo_password:
        wanted += [(u, name, "user", settings.seed_demo_password) for u, name in DEMO_USERS]
    else:
        log.warning("seed_demo_skipped", reason="SEED_DEMO_PASSWORD is empty")

    existing = set(await db.scalars(select(User.username)))
    created = []
    for username, display_name, role, password in wanted:
        if username in existing:
            continue
        db.add(
            User(
                username=username,
                display_name=display_name,
                role=role,
                password_hash=hash_password(password),
                language="th",
            )
        )
        created.append(username)
    await db.commit()
    return created


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, settings.service_name)
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as db:
            created = await seed_users(db, settings)
        log.info("seed_done", created=created)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
