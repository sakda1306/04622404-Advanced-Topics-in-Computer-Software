"""Small orchestration facade for adapters or an eventual HTTP layer."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from .knowledge import retrieve_knowledge
from .models import KnowledgePassage, KnowledgeResult, RiskResult, RouteResult
from .risk import RiskThresholds, assess_risk
from .routing import analyze_routes


class RiskKnowledgeService:
    def __init__(
        self,
        *,
        passages: Iterable[KnowledgePassage | dict[str, Any]] = (),
        thresholds: RiskThresholds = RiskThresholds(),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._passages = [
            item if isinstance(item, KnowledgePassage) else KnowledgePassage.model_validate(item)
            for item in passages
        ]
        self._thresholds = thresholds
        self._clock = clock

    async def risk(self, query: Any, context: Any) -> RiskResult:
        # Query is accepted for interface compatibility; risk features live in context.
        del query
        return assess_risk(context, thresholds=self._thresholds, now=self._clock())

    async def knowledge(self, query: Any, alerts: list[Any]) -> KnowledgeResult:
        return retrieve_knowledge(query, alerts, self._passages, now=self._clock())

    async def routes(self, query: Any, context: Any, risk: Any) -> RouteResult:
        return analyze_routes(query, context, risk, now=self._clock())
