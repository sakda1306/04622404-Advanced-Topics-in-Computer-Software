"""Builders for Agent contract objects used in tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.ids import new_id
from app.infrastructure.agent.contracts import (
    AgentLimits,
    AgentLocation,
    AgentRunRequest,
    AgentTravelRequest,
    AgentUserProfile,
    IntentHint,
)


def run_request(run_id: UUID | None = None, *, deadline: datetime | None = None) -> AgentRunRequest:
    deadline = deadline or datetime.now(UTC) + timedelta(seconds=30)
    return AgentRunRequest(
        run_id=run_id or new_id(),
        intent_hint=IntentHint.CHECK_SAFETY,
        request=AgentTravelRequest(
            origin=AgentLocation(lat=13.7563, lon=100.5018, name="Bangkok"),
            destination=AgentLocation(lat=18.7883, lon=98.9853, name="Chiang Mai"),
            departure_time=datetime(2026, 9, 20, 1, 0, tzinfo=UTC),
            timezone="Asia/Bangkok",
            language="th",
        ),
        user_profile=AgentUserProfile(pseudonymous_id="p-123", language="th"),
        limits=AgentLimits(deadline_at=deadline, max_tool_calls=20),
    )


def run_response(run_id: UUID, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "run_id": str(run_id),
        "status": "completed",
        "risk": {"level": "LOW", "score": 0.1, "confidence": 0.9, "factors": []},
        "recommendation": {"type": "TRAVEL_NORMALLY", "summary": "ok", "reasons": []},
        "service_status": {"weather": "ok", "disaster": "ok"},
        "data_freshness": {
            "items": [{"category": "WEATHER", "updated_at": "2026-09-17T08:00:00Z"}]
        },
        "versions": {"agent": "test"},
        "diagnostics": {"tool_calls": 3, "duration_ms": 10, "trace_id": "t"},
    }
    body.update(overrides)
    return body
