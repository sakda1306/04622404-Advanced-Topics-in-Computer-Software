"""Redis connections: core (noeviction) and cache (allkeys-lru), see D-14.

`broker` is the Celery broker database; the API only reads queue lengths from it.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.config import RedisSettings


@dataclass
class RedisClients:
    core: Redis
    cache: Redis
    broker: Redis | None = None

    async def aclose(self) -> None:
        await self.core.aclose()
        await self.cache.aclose()
        if self.broker is not None:
            await self.broker.aclose()


def _client(url: str, settings: RedisSettings) -> Redis:
    client: Redis = Redis.from_url(
        url,
        socket_timeout=settings.redis_socket_timeout_seconds,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        health_check_interval=30,
    )
    return client


def create_redis_clients(settings: RedisSettings) -> RedisClients:
    return RedisClients(
        core=_client(settings.core_url(), settings),
        cache=_client(settings.cache_url(), settings),
        broker=_client(settings.broker_url(), settings),
    )
