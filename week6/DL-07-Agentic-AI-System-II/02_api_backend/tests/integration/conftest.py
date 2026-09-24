"""PostGIS container shared by the integration tests.

Each test module gets its own database, so migration tests (which drop tables) never
interfere with data tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest
from alembic import command
from alembic.config import Config
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from tests.integration.flow import Flow

POSTGIS_IMAGE = "postgis/postgis:16-3.4"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class PgServer:
    host: str
    port: int
    user: str = "tsa"
    password: str = "tsa"

    def dsn(self, database: str) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{database}"

    def sqlalchemy_url(self, database: str) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{database}"
        )


@pytest.fixture(scope="session")
def pg_server() -> Iterator[PgServer]:
    try:
        from testcontainers.community.postgres import PostgresContainer

        container = PostgresContainer(
            POSTGIS_IMAGE, username="tsa", password="tsa", dbname="tsa", driver=None
        )
        container.start()
    except Exception as exc:  # Docker not running or image not available
        pytest.skip(f"PostGIS container unavailable: {type(exc).__name__}")
    try:
        yield PgServer(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(5432)),
        )
    finally:
        container.stop()


def create_database(server: PgServer) -> str:
    name = f"test_{uuid4().hex[:12]}"

    async def _create() -> None:
        conn = await asyncpg.connect(server.dsn("tsa"))
        try:
            await conn.execute(f'CREATE DATABASE "{name}"')
        finally:
            await conn.close()

    asyncio.run(_create())
    return name


def alembic_config(url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.attributes["database_url"] = url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="module")
def empty_db_url(pg_server: PgServer) -> str:
    return pg_server.sqlalchemy_url(create_database(pg_server))


@pytest.fixture(scope="module")
def migrated_db_url(empty_db_url: str) -> str:
    command.upgrade(alembic_config(empty_db_url), "head")
    return empty_db_url


@pytest.fixture
async def engine(migrated_db_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session whose work is always rolled back, so tests stay independent."""
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Committing sessions with reference data; tests isolate themselves with fresh users."""
    from app.infrastructure.db.reference_data import seed_reference_data

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await seed_reference_data(session)
        await session.commit()
    return sessions


@pytest.fixture
async def flow(
    session_factory: async_sessionmaker[AsyncSession],
    redis: FakeAsyncRedis,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> Flow:
    from app.core.logging import configure_logging
    from app.infrastructure.db.repositories.recommendations import SqlRecommendationRepository
    from app.infrastructure.redis.cache import RedisRecommendationCache
    from app.infrastructure.redis.job_state import RedisJobStateStore
    from app.infrastructure.redis.keys import RedisKeys
    from app.infrastructure.redis.slots import RedisSlotLimiter
    from app.infrastructure.redis.tickets import RedisTicketStore
    from mock_agent.main import MockState
    from tests.integration.flow import build_agent

    configure_logging("INFO", json_output=True)
    monkeypatch.delenv("MOCK_REQUIRE_TOKEN", raising=False)
    monkeypatch.setenv("MOCK_STEP_DELAY_SECONDS", "0")
    state = MockState()
    keys = RedisKeys("test")
    agent = build_agent(state, redis, settings)
    return Flow(
        settings=settings,
        repo=SqlRecommendationRepository(session_factory),
        redis=redis,
        keys=keys,
        jobs=RedisJobStateStore(redis, keys, ttl_seconds=3600),
        slots=RedisSlotLimiter(redis),
        tickets=RedisTicketStore(redis, keys),
        cache=RedisRecommendationCache(redis, keys),
        agent_state=state,
        agent=agent,
    )
