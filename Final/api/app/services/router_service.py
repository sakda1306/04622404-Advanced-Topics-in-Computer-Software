"""One chat message through quota, the router and `router_log` (PRD FR-13, FR-23; Contract §2.4).

The request stays counted for the route's answer step, which adds its own tokens on `quota_day`.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.ids import request_id_var
from app.core.logging import get_logger
from app.infra.jev import JevClient
from app.infra.llm import GroqClient
from app.infra.models import RouterLog
from app.router.decide import decide
from app.router.decision import Decision
from app.services import quota_service

log = get_logger(__name__)

# Blocks a user with no tokens left, which `reserve` alone allows at exactly the limit.
_MIN_TOKENS_LEFT = 1


@dataclass(frozen=True, slots=True)
class RoutedMessage:
    decision: Decision
    quota_day: date


async def route_message(
    db: AsyncSession,
    llm: GroqClient,
    settings: Settings,
    *,
    user_id: str,
    message: str,
    has_profile: bool,
    recent: Sequence[dict[str, str]] = (),
    jev: JevClient | None = None,
) -> RoutedMessage:
    """Raises QUOTA_EXCEEDED before any LLM call; any failure after that comes with a refund."""
    day = await quota_service.reserve(db, user_id, settings, estimated_tokens=_MIN_TOKENS_LEFT)
    started = time.perf_counter()
    try:
        decision = await decide(
            message, has_profile=has_profile, llm=llm, user_id=user_id, recent=recent, jev=jev
        )
    except Exception:
        await quota_service.refund(db, user_id, day)
        raise
    latency_ms = round((time.perf_counter() - started) * 1000)
    if decision.tokens:
        await quota_service.add_tokens(db, user_id, day, decision.tokens)
    await _record(db, user_id, decision, latency_ms)
    return RoutedMessage(decision=decision, quota_day=day)


async def _record(db: AsyncSession, user_id: str, decision: Decision, latency_ms: int) -> None:
    try:
        db.add(
            RouterLog(
                request_id=request_id_var.get(),
                user_id=user_id,
                route=decision.route,
                layer=decision.layer,
                confidence=decision.confidence,
                latency_ms=latency_ms,
                tokens=decision.tokens,
            )
        )
        await db.commit()
    except Exception as problem:  # a debugging log must never cost the user their answer
        await db.rollback()
        log.warning("router_log_failed", error_type=type(problem).__name__)
