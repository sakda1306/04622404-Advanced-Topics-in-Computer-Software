"""The agent run: a fixed sequence of nodes over one AgentState (02_step.txt).

Each node is a plain async function so the sequence can move onto a LangGraph state
graph later without changing the nodes. The agent collects evidence and calls Module 07;
it never chooses the travel action itself (03_process.txt).
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from travel_agent.budget import AgentError, Budget
from travel_agent.config import Settings
from travel_agent.contracts import (
    AgentRunRequest,
    AgentRunResponse,
    Clarification,
    IntentHint,
    JobStage,
    ServiceState,
)
from travel_agent.evidence import build_decision_request
from travel_agent.response import build_response
from travel_agent.routes import timed_routes as build_timed_routes
from travel_agent.tools.base import ALLOWED_TOOLS, ToolError, ToolSet
from travel_agent.tools.decision import DecisionClient, DecisionResult
from travel_agent.tools.schemas import (
    DisasterResult,
    IntegratedContext,
    KnowledgeResult,
    Record,
    RiskResult,
    RouteCandidatesResult,
    RouteResult,
    TransportResult,
    TravelQuery,
    WeatherResult,
)

log = logging.getLogger("travel_agent")

T = TypeVar("T")
Emit = Callable[[JobStage, int, str], Awaitable[None]]


@dataclass
class AgentState:
    """Everything one run knows. Holds no user identity and no raw question text."""

    run: AgentRunRequest
    query: TravelQuery
    budget: Budget
    intent: IntentHint
    started: float = field(default_factory=time.monotonic)
    weather: WeatherResult | None = None
    transport: TransportResult | None = None
    disasters: DisasterResult | None = None
    candidates: RouteCandidatesResult | None = None
    # 04's candidates with the enter/exit times the agent derived; 05's input.
    timed_routes: list[dict[str, Any]] = field(default_factory=list)
    context: IntegratedContext | None = None
    risk: RiskResult | None = None
    knowledge: KnowledgeResult | None = None
    routes: RouteResult | None = None
    decision: DecisionResult | None = None
    service_status: dict[str, ServiceState] = field(
        default_factory=lambda: dict.fromkeys(ALLOWED_TOOLS.values(), ServiceState.NOT_USED)
    )
    trace: list[dict[str, Any]] = field(default_factory=list)
    _record_ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    def records(self) -> list[Record]:
        found: list[Record] = []
        for result in (self.weather, self.transport, self.disasters, self.candidates, self.risk):
            if result:
                found.extend(result.records)
        if self.disasters:
            found.extend(alert.record for alert in self.disasters.alerts)
        for result in (self.knowledge, self.routes):
            if result:
                found.extend(result.records)
        return found


class Agent:
    def __init__(self, settings: Settings, tools: ToolSet, decision: DecisionClient) -> None:
        self._settings = settings
        self._tools = tools
        self._decision = decision

    async def run(self, run: AgentRunRequest, emit: Emit) -> AgentRunResponse:
        request = run.request
        preferences = request.preferences
        modes = preferences.get("travel_modes")
        scenario = preferences.get("mock_scenario")
        state = AgentState(
            run=run,
            intent=run.intent_hint,
            budget=Budget(
                max_steps=self._settings.max_agent_steps,
                max_tool_calls=min(self._settings.max_tool_calls, run.limits.max_tool_calls),
            ),
            query=TravelQuery(
                run_id=str(run.run_id),
                origin=(request.origin.lat, request.origin.lon),
                destination=(request.destination.lat, request.destination.lon),
                departure_time=request.departure_time,
                travel_modes=[m for m in modes if isinstance(m, str)]
                if isinstance(modes, list)
                else [],
                mock_scenario=scenario if isinstance(scenario, str) else None,
            ),
        )
        try:
            state.budget.step()
            clarification = understand(state)
            if clarification:
                return self._finish(state, clarification=clarification)

            await emit(JobStage.FETCHING_DATA, 10, "Checking weather, transport and alerts")
            state.budget.step()
            await self._fetch_external(state)
            state.budget.step()
            await self._integrate(state)

            await emit(JobStage.ASSESSING_RISK, 40, "Assessing route risk")
            state.budget.step()
            await self._assess(state)

            await emit(JobStage.GENERATING_ADVICE, 70, "Preparing the recommendation")
            state.budget.step()
            await self._decide(state)
            return self._finish(state)
        finally:
            _log_trace(state)

    # ------------------------------------------------------------------ nodes

    async def _fetch_external(self, state: AgentState) -> None:
        # Module 04: the three sources are independent, so call them in parallel.
        # Reserve the budget up front so a limit cannot stop one call after others started.
        query = state.query
        state.budget.reserve_tool_calls(4)
        state.weather, state.transport, state.disasters, state.candidates = await asyncio.gather(
            self._call(state, "weather", lambda: self._tools.weather(query), reserved=True),
            self._call(state, "transport", lambda: self._tools.transport(query), reserved=True),
            self._call(state, "disasters", lambda: self._tools.disasters(query), reserved=True),
            self._call(
                state,
                "route_candidates",
                lambda: self._tools.route_candidates(query),
                reserved=True,
            ),
        )
        # Module 05 matches evidence to a route by time, so it needs the ETA per stretch.
        if state.candidates:
            state.timed_routes = build_timed_routes(
                state.candidates.candidates, state.run.request.departure_time
            )

    async def _integrate(self, state: AgentState) -> None:
        state.context = await self._call(
            state,
            "integrate",
            lambda: self._tools.integrate(
                state.query,
                state.timed_routes,
                state.weather,
                state.transport,
                state.disasters,
            ),
        )

    async def _assess(self, state: AgentState) -> None:
        # Module 06, in order: route analysis uses the risk result.
        query = state.query
        state.risk = await self._call(state, "risk", lambda: self._tools.risk(query, state.context))
        alerts = state.disasters.alerts if state.disasters else []
        state.knowledge = await self._call(
            state, "knowledge", lambda: self._tools.knowledge(query, alerts)
        )
        state.routes = await self._call(
            state, "routes", lambda: self._tools.routes(query, state.context, state.risk)
        )

    async def _decide(self, state: AgentState) -> None:
        payload = build_decision_request(state)
        state.decision = await self._call(
            state,
            "decide",
            lambda: self._decision.decide(payload, timeout=self._settings.tool_timeout_seconds),
        )
        if state.decision is None:
            raise AgentError("DECISION_UNAVAILABLE", "Module 07 did not return a decision", 503)
        if state.decision.request_id != state.run.run_id:
            raise AgentError("DECISION_MISMATCH", "Module 07 answered a different request", 503)

    # ------------------------------------------------------------------ helpers

    async def _call(
        self,
        state: AgentState,
        name: str,
        call: Callable[[], Awaitable[T]],
        *,
        reserved: bool = False,
    ) -> T | None:
        """Run one allowlisted tool. A failure marks its service unavailable instead of
        ending the run, so one provider cannot take the whole answer down."""
        service = ALLOWED_TOOLS[name]
        if not reserved:
            state.budget.reserve_tool_calls()
        started = time.monotonic()
        outcome = "ok"
        try:
            async with asyncio.timeout(self._settings.tool_timeout_seconds):
                result = await call()
            result = _number_records(result, name, state._record_ids)
            state.service_status[service] = ServiceState.OK
            return result
        except TimeoutError:
            outcome = "timeout"
        except ToolError as error:
            outcome = f"error: {error.reason}"
        except Exception:  # noqa: BLE001 - bulkhead: a buggy tool must not end the run
            log.exception("tool %s raised", name)
            outcome = "error: unexpected"
        finally:
            state.trace.append(
                {"tool": name, "outcome": outcome, "ms": int((time.monotonic() - started) * 1000)}
            )
        state.service_status[service] = ServiceState.UNAVAILABLE
        return None

    def _finish(
        self, state: AgentState, clarification: Clarification | None = None
    ) -> AgentRunResponse:
        return build_response(
            state,
            settings=self._settings,
            clarification=clarification,
            duration_ms=int((time.monotonic() - state.started) * 1000),
        )


def understand(state: AgentState) -> Clarification | None:
    """Intent and required-slot check. Ask instead of guessing (02_step.txt step 4).

    Intent currently comes from Module 02's hint; the LLM classifier comes later.
    """
    request = state.run.request
    thai = request.language.lower().startswith("th")
    same_place = (round(request.origin.lat, 4), round(request.origin.lon, 4)) == (
        round(request.destination.lat, 4),
        round(request.destination.lon, 4),
    )
    if same_place:
        return Clarification(
            question="ต้นทางและปลายทางเป็นจุดเดียวกัน ต้องการเดินทางไปที่ไหน?"
            if thai
            else "The origin and destination are the same place. Where are you going?",
            missing_fields=["destination"],
        )
    if request.departure_time < datetime.now(UTC) - timedelta(hours=1):
        return Clarification(
            question="เวลาออกเดินทางผ่านไปแล้ว ต้องการออกเดินทางเมื่อไร?"
            if thai
            else "That departure time has passed. When do you want to leave?",
            missing_fields=["departure_time"],
        )
    return None


def _number_records[R](result: R, tool: str, counter: itertools.count) -> R:
    """Give every record a run-unique evidence ID so citations can point back to it."""

    def numbered(record: Record) -> Record:
        return record.model_copy(update={"id": f"{tool}-{next(counter)}"})

    updates: dict[str, Any] = {}
    if records := getattr(result, "records", None):
        updates["records"] = [numbered(r) for r in records]
    if isinstance(result, DisasterResult):
        updates["alerts"] = [
            a.model_copy(update={"record": numbered(a.record)}) for a in result.alerts
        ]
    return result.model_copy(update=updates) if updates else result


def _log_trace(state: AgentState) -> None:
    # Tool names, outcomes and timings only: no coordinates, question text or user data.
    log.info(
        json.dumps(
            {
                "event": "agent_run",
                "run_id": str(state.run.run_id),
                "intent": state.intent.value,
                "steps": state.budget.steps,
                "tool_calls": state.budget.tool_calls,
                "trace": state.trace,
                "action": state.decision.action_code if state.decision else None,
            }
        )
    )
