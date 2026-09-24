from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import DatabaseSettings
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.session import create_engine, create_session_factory, session_scope
from tests.integration import factories as f

pytestmark = pytest.mark.integration


def _settings(url: str) -> DatabaseSettings:
    return DatabaseSettings(database_url=SecretStr(url), db_pool_size=2, db_max_overflow=0)


async def test_engine_uses_utc_and_application_name(migrated_db_url: str) -> None:
    engine = create_engine(_settings(migrated_db_url))
    try:
        async with engine.connect() as conn:
            tz = (await conn.execute(text("SHOW timezone"))).scalar_one()
            app_name = (await conn.execute(text("SHOW application_name"))).scalar_one()
    finally:
        await engine.dispose()

    assert tz == "UTC"
    assert app_name == "tsa-api"


async def test_session_scope_commits_on_success(migrated_db_url: str) -> None:
    engine = create_engine(_settings(migrated_db_url))
    factory = create_session_factory(engine)
    user = f.user()
    try:
        async for session in session_scope(factory):
            session.add(user)

        async with factory() as check:
            found = await check.get(UserModel, user.id)
            assert found is not None
            await check.delete(found)
            await check.commit()
    finally:
        await engine.dispose()


async def test_session_scope_rolls_back_on_error(migrated_db_url: str) -> None:
    engine = create_engine(_settings(migrated_db_url))
    factory = create_session_factory(engine)
    user = f.user()
    try:
        scope = session_scope(factory)
        session = await anext(scope)
        session.add(user)
        await session.flush()
        with pytest.raises(RuntimeError):
            await scope.athrow(RuntimeError("boom"))

        async with factory() as check:
            count = await check.scalar(
                select(func.count()).select_from(UserModel).where(UserModel.id == user.id)
            )
        assert count == 0
    finally:
        await engine.dispose()


async def test_database_errors_do_not_contain_parameters(migrated_db_url: str) -> None:
    # SQLAlchemy must not append bound values; driver text is redacted when logged
    # (tests/unit/test_logging.py).
    engine = create_engine(_settings(migrated_db_url))
    secret = "question-with-personal-data"
    try:
        async with engine.connect() as conn:
            with pytest.raises(DBAPIError) as info:
                await conn.execute(text("SELECT CAST(:value AS integer)"), {"value": secret})
    finally:
        await engine.dispose()

    assert "[SQL parameters hidden due to hide_parameters=True]" in str(info.value)
