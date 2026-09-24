"""The only place Redis key formats are defined (docs/03_data_design.md section 5.2).

Key parts that come from users are always hashed, so no personal data or raw
client input ends up in a key name.
"""

from __future__ import annotations

from uuid import UUID

from app.core.crypto import sha256_hex


class RedisKeys:
    def __init__(self, env: str) -> None:
        self._prefix = f"tsa:{env}:"

    def rate_limit(self, scope: str, subject_hash: str) -> str:
        return f"{self._prefix}rl:{scope}:{subject_hash}"

    def circuit_breaker(self, name: str) -> str:
        return f"{self._prefix}cb:{name}"

    def idempotency(self, principal_hash: str, method: str, route: str, key: str) -> str:
        route_hash = sha256_hex(route.encode())[:16]
        key_hash = sha256_hex(key.encode())
        return f"{self._prefix}idem:{principal_hash}:{method.upper()}:{route_hash}:{key_hash}"

    def idempotency_pattern(self, principal_hash: str) -> str:
        """SCAN pattern for every stored response of one caller."""
        return f"{self._prefix}idem:{principal_hash}:*"

    def job(self, job_id: UUID) -> str:
        return f"{self._prefix}job:{job_id}"

    def job_events(self, job_id: UUID) -> str:
        return f"{self._prefix}job:{job_id}:events"

    def active_jobs(self, user_id: UUID) -> str:
        return f"{self._prefix}jobs:active:{user_id}"

    def streams(self, user_id: UUID) -> str:
        return f"{self._prefix}streams:{user_id}"

    def stream_ticket(self, ticket: str) -> str:
        # The ticket is a bearer secret, so only its hash appears in the key (D-40).
        return f"{self._prefix}sse:ticket:{sha256_hex(ticket.encode())}"

    def cooldown(self, name: str) -> str:
        """One-at-a-time claims: `export:{user_id}` (P-63), `purge` (data design 5.2)."""
        return f"{self._prefix}lock:{name}"

    def recommendation_cache(self, cache_key: str) -> str:
        return f"{self._prefix}reco:{cache_key}"

    def service_reports(self) -> str:
        """Latest state of each data service as reported by the Agent (E-23)."""
        return f"{self._prefix}status:reports"

    def service_status(self) -> str:
        return f"{self._prefix}status:service"

    def ready_agent(self) -> str:
        return f"{self._prefix}ready:agent"
