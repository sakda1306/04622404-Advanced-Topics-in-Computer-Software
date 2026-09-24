"""HTTP client for Module 07 (`POST /v1/decisions`, decision_engine/models.py)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from travel_agent.contracts import RecommendationType, RiskLevel
from travel_agent.tools.base import ToolError

DECISIONS_PATH = "/v1/decisions"
_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


class _Lenient(BaseModel):
    # Module 07 may add fields; we only type-check what we use.
    model_config = ConfigDict(extra="ignore", frozen=True)


class Explanation(_Lenient):
    summary: str
    reasons: list[str]
    instructions: list[str]
    uncertainty: list[str]


class Citation(_Lenient):
    evidence_id: str
    source_name: str
    url: str
    fetched_at: datetime


class Versions(_Lenient):
    policy: str
    risk_model: str | None


class EmergencyContact(_Lenient):
    # Same four fields as Module 02's contract; 07 keeps its catalog metadata separate.
    name: str
    phone: str
    url: str | None = None
    available_hours: str | None = None


class EmergencyInstructions(_Lenient):
    what_to_do_now: str
    safety_steps: list[str] = Field(default_factory=list)
    contacts: list[EmergencyContact] = Field(default_factory=list)
    nearest_support: list[dict] = Field(default_factory=list)


class EmergencyAssessment(_Lenient):
    # "not_required" unless the action is AVOID; "grounded" from a reviewed procedure,
    # "fallback" from 07's generic text.
    status: Literal["not_required", "grounded", "fallback"]
    issues: list[str] = Field(default_factory=list)


class DecisionResult(_Lenient):
    request_id: UUID
    action_code: Literal["NORMAL", "CHANGE_ROUTE", "DELAY", "AVOID"]
    backend_action_code: RecommendationType
    risk_level: RiskLevel | None
    escalation_required: bool
    selected_route_id: str | None
    suggested_departure_time: datetime | None
    explanation: Explanation
    citations: list[Citation]
    versions: Versions
    valid_until: datetime | None
    # Present only when 07 locks AVOID (integration-v3). The agent passes the object
    # through untouched; it never writes or edits emergency text itself.
    emergency_instructions: EmergencyInstructions | None = None
    emergency_assessment: EmergencyAssessment | None = None
    # Catalog provenance per contact index ("0", "1", ...). Module 02's response has no
    # field for it yet, so the agent only logs it — see README for the open question.
    emergency_contact_metadata: dict[str, dict] = Field(default_factory=dict)


class _RetryableStatus(Exception):
    pass


def _retryable(error: BaseException) -> bool:
    return isinstance(error, httpx.TransportError | _RetryableStatus)


class DecisionClient:
    def __init__(self, http: httpx.AsyncClient, *, base_url: str, max_attempts: int) -> None:
        self._http = http
        self._url = base_url.rstrip("/") + DECISIONS_PATH
        self._max_attempts = max_attempts

    async def decide(self, payload: dict[str, Any], *, timeout: float) -> DecisionResult:
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_retryable),
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_exponential_jitter(initial=0.2, max=1),
                reraise=True,
            ):
                with attempt:
                    response = await self._http.post(self._url, json=payload, timeout=timeout)
                    if response.status_code in _RETRYABLE_STATUS:
                        raise _RetryableStatus(str(response.status_code))
        except (httpx.TransportError, _RetryableStatus) as error:
            raise ToolError("decide", f"unavailable ({type(error).__name__})") from error

        if response.status_code != 200:
            # 422 means our evidence package broke 07's contract: a bug on our side.
            raise ToolError("decide", f"HTTP {response.status_code}")
        try:
            return DecisionResult.model_validate_json(response.content)
        except ValidationError as error:
            raise ToolError("decide", "response failed schema validation") from error
