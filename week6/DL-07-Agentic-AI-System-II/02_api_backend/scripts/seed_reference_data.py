"""Seed reference data: `python -m scripts.seed_reference_data` (needs DATABASE_URL)."""

from __future__ import annotations

import asyncio
import sys

from app.core.config import DatabaseSettings
from app.infrastructure.db.reference_data import seed_reference_data
from app.infrastructure.db.session import create_engine, create_session_factory


async def _main() -> None:
    engine = create_engine(DatabaseSettings())
    try:
        async with create_session_factory(engine)() as session, session.begin():
            counts = await seed_reference_data(session)
    finally:
        await engine.dispose()
    print(f"seeded reference data: {counts}")


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
