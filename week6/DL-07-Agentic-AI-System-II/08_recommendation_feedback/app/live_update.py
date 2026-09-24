"""
Live update mechanism — Redis-backed dedup/cooldown/consent gating for
alert delivery. Connects to the real Redis container by default; a
FakeRedis stand-in is still available for unit tests that shouldn't need
a running Redis instance.

Rules encoded here (from 02_step.txt / 03_process.txt):
- Live updates are sent ONLY with user consent.
- Deduplication + cooldown reduce notification fatigue.
- An alert must NEVER be suppressed if its severity has increased,
  even if it would otherwise be inside a cooldown window.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.config import settings
from app.schema import RiskLevel
import structlog

logger = structlog.get_logger("live_update")

try:
    import redis.asyncio as redis_asyncio
except ImportError:  # pragma: no cover
    redis_asyncio = None

_RISK_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
}

# Redis may still hold values written before the 3-level change. Map them
# instead of crashing, so a stale key can never suppress or break an alert.
_LEGACY_RISK_ALIASES = {"MODERATE": "MEDIUM", "CRITICAL": "HIGH"}


def _parse_risk(raw: Optional[str]) -> Optional[RiskLevel]:
    if not raw:
        return None
    try:
        return RiskLevel(_LEGACY_RISK_ALIASES.get(raw, raw))
    except ValueError:
        return None


@dataclass
class AlertEvent:
    user_id: str
    request_id: str
    risk_level: RiskLevel
    message: str
    timestamp: float = field(default_factory=time.time)


class FakeRedis:
    """In-memory stand-in with the same minimal get/set surface used here.
    Used only by tests that should not depend on a running Redis instance."""

    def __init__(self):
        self._store: Dict[str, str] = {}

    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def set(self, key: str, value: str) -> None:
        self._store[key] = value


def _make_default_redis_client():
    if redis_asyncio is not None:
        return redis_asyncio.Redis.from_url(settings.redis_url, decode_responses=True)
    return FakeRedis()


class LiveUpdateBroker:
    def __init__(self, cooldown_seconds: int = 300, redis_client=None):
        self.cooldown_seconds = cooldown_seconds
        self.redis = redis_client if redis_client is not None else _make_default_redis_client()
        self._consented_users: set[str] = set()
        self._sent_log: List[AlertEvent] = []  # for tests/inspection only

    def grant_consent(self, user_id: str) -> None:
        self._consented_users.add(user_id)

    def revoke_consent(self, user_id: str) -> None:
        self._consented_users.discard(user_id)

    def has_consent(self, user_id: str) -> bool:
        return user_id in self._consented_users

    @staticmethod
    def _last_sent_key(user_id: str) -> str:
        return f"live_update:last_sent:{user_id}"

    @staticmethod
    def _last_risk_key(user_id: str) -> str:
        return f"live_update:last_risk:{user_id}"

    async def should_send(self, event: AlertEvent) -> bool:
        if not self.has_consent(event.user_id):
            return False

        last_sent_raw = await self.redis.get(self._last_sent_key(event.user_id))
        last_risk_raw = await self.redis.get(self._last_risk_key(event.user_id))

        if last_sent_raw is None:
            return True

        last_sent = float(last_sent_raw)
        within_cooldown = (event.timestamp - last_sent) < self.cooldown_seconds

        if not within_cooldown:
            return True

        # Never suppress an increase in severity, even inside cooldown.
        last_risk = _parse_risk(last_risk_raw)
        last_rank = _RISK_RANK[last_risk] if last_risk is not None else -1
        current_rank = _RISK_RANK[event.risk_level]
        return current_rank > last_rank

    async def publish(self, event: AlertEvent) -> bool:
        """Returns True if the event was actually sent (after dedup/cooldown/consent checks)."""
        if not await self.should_send(event):
            return False

        await self.redis.set(self._last_sent_key(event.user_id), str(event.timestamp))
        await self.redis.set(self._last_risk_key(event.user_id), event.risk_level.value)
        self._sent_log.append(event)

        # In production: also publish to a channel a WebSocket/SSE gateway
        # subscribes to, e.g. await self.redis.publish(f"user:{event.user_id}:alerts", ...)
        return True

    def sent_log(self) -> List[AlertEvent]:
        return list(self._sent_log)


def dispatch_notification(
    user_id: str,
    message: str,
    channel: str = "in_app",
) -> bool:
    """
    Dispatch notification to configured providers.
    If no keys configured, safely no-op with structured log.
    """
    provider_keys = [k.strip() for k in settings.notification_provider_keys.split(",") if k.strip()]
    if not provider_keys:
        logger.info(
            "notification_dispatched_noop",
            user_id=user_id,
            channel=channel,
            reason="no_provider_keys_configured",
        )
        return True

    # Real provider hooks would go here once provider SDKs are added
    logger.info("notification_dispatched_external", user_id=user_id, channel=channel)
    return True
