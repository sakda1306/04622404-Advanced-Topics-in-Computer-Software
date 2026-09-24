"""Build the AgentClient the same way in the API and in workers."""

from __future__ import annotations

import httpx
from redis.asyncio import Redis

from app.core.config import Settings
from app.infrastructure.agent.auth import build_token_provider
from app.infrastructure.agent.circuit_breaker import RedisCircuitBreaker
from app.infrastructure.agent.client import AgentClient
from app.infrastructure.redis.keys import RedisKeys


def build_agent_client(
    settings: Settings, http: httpx.AsyncClient, redis: Redis, keys: RedisKeys
) -> AgentClient:
    agent = settings.agent
    return AgentClient(
        http,
        settings=agent,
        tokens=build_token_provider(agent, http),
        breaker=RedisCircuitBreaker(
            redis,
            name=keys.circuit_breaker("agent"),
            failure_threshold=agent.agent_cb_failure_threshold,
            window_seconds=agent.agent_cb_window_seconds,
            reset_seconds=agent.agent_cb_reset_seconds,
        ),
        user_agent=f"tsa-backend/{settings.app.api_version}",
    )
