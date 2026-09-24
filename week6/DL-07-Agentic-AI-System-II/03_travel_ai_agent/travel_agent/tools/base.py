"""The fixed set of tools the agent may call.

The agent never builds URLs or commands itself: every capability is a method on a
ToolSet, and the pipeline can only call names listed in ALLOWED_TOOLS.
"""

from __future__ import annotations

from typing import Protocol

from travel_agent.tools.schemas import (
    Alert,
    DisasterResult,
    IntegratedContext,
    KnowledgeResult,
    RiskResult,
    RouteCandidatesResult,
    RouteResult,
    TransportResult,
    TravelQuery,
    WeatherResult,
)

# Tool name -> service key reported in service_status. Module 02 shows only the keys in
# its D-47 list (weather, transport, disaster, risk_model, rag, llm) and ignores the rest.
# "llm" is not reported until the agent has a real LLM planner.
ALLOWED_TOOLS: dict[str, str] = {
    "weather": "weather",
    "transport": "transport",
    "disasters": "disaster",
    # Own key: sharing one with 06's "routes" would let a later success hide this failure.
    "route_candidates": "route_candidates",
    "integrate": "integration",
    "risk": "risk_model",
    "knowledge": "rag",
    "routes": "route",
    "decide": "decision",
}


class ToolError(Exception):
    """A tool failed or returned data that did not pass validation."""

    def __init__(self, tool: str, reason: str) -> None:
        super().__init__(f"{tool}: {reason}")
        self.tool = tool
        self.reason = reason


class ToolSet(Protocol):
    # Module 04 — external data
    async def weather(self, query: TravelQuery) -> WeatherResult: ...
    async def transport(self, query: TravelQuery) -> TransportResult: ...
    async def disasters(self, query: TravelQuery) -> DisasterResult: ...
    async def route_candidates(self, query: TravelQuery) -> RouteCandidatesResult: ...

    # Module 05 — data integration. `routes` carries each candidate's geometry with the
    # enter/exit times the agent derived from 04's leg durations; inputs are None when
    # that source failed.
    async def integrate(
        self,
        query: TravelQuery,
        routes: list[dict],
        weather: WeatherResult | None,
        transport: TransportResult | None,
        disasters: DisasterResult | None,
    ) -> IntegratedContext: ...

    # Module 06 — risk model, Disaster RAG and route analysis
    async def risk(self, query: TravelQuery, context: IntegratedContext | None) -> RiskResult: ...
    async def knowledge(self, query: TravelQuery, alerts: list[Alert]) -> KnowledgeResult: ...
    async def routes(
        self, query: TravelQuery, context: IntegratedContext | None, risk: RiskResult | None
    ) -> RouteResult: ...
