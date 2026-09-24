"""Dependency checks for /ready and the Celery queue depth for /metrics."""

from __future__ import annotations

from collections.abc import Sequence

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Kombu's Redis transport keeps one list per queue and priority step (0 is the plain name).
_PRIORITY_SEPARATOR = "\x06\x16"
_PRIORITY_STEPS = (3, 6, 9)


async def database_ok(engine: AsyncEngine) -> bool:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


async def redis_ok(client: Redis) -> bool:
    return bool(await client.ping())


async def queue_depth(broker: Redis, queues: Sequence[str]) -> dict[str, int]:
    """Messages waiting in each queue (not counting ones a worker already holds)."""
    async with broker.pipeline(transaction=False) as pipe:
        for queue in queues:
            pipe.llen(queue)
            for step in _PRIORITY_STEPS:
                pipe.llen(f"{queue}{_PRIORITY_SEPARATOR}{step}")
        lengths = await pipe.execute()
    per_queue = 1 + len(_PRIORITY_STEPS)
    return {
        queue: sum(int(n) for n in lengths[i * per_queue : (i + 1) * per_queue])
        for i, queue in enumerate(queues)
    }
