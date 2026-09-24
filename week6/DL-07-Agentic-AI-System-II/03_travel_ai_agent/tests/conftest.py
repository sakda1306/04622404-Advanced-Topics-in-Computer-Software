from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from decision_engine.api import create_app as create_decision_app
from decision_engine.config import Settings as DecisionSettings

from travel_agent.api import create_app
from travel_agent.config import Settings


def run_body(scenario: str | None = None, **overrides) -> dict:
    """A valid AgentRunRequest as Module 02 would send it."""
    now = datetime.now(UTC)
    preferences = {"mock_scenario": scenario} if scenario else {}
    body = {
        "run_id": str(uuid4()),
        "intent_hint": "CHECK_SAFETY",
        "request": {
            "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
            "destination": {"lat": 12.5684, "lon": 99.9577, "name": "Hua Hin"},
            "departure_time": (now + timedelta(hours=2)).isoformat(),
            "timezone": "Asia/Bangkok",
            "language": "th",
            "preferences": preferences,
            "question": "ไปหัวหินพรุ่งนี้ปลอดภัยไหม",
        },
        "context": {"messages": []},
        "user_profile": {"pseudonymous_id": "u_test", "language": "th", "home_region": "TH"},
        "limits": {"deadline_at": (now + timedelta(seconds=30)).isoformat(), "max_tool_calls": 20},
    }
    body.update(overrides)
    return body


@pytest.fixture
def decision_http(tmp_path):
    """The real Module 07 engine, served in-process."""
    decision_app = create_decision_app(DecisionSettings(audit_log_path=tmp_path / "audit.jsonl"))
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=decision_app), base_url="http://decision"
    )


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        decision_service_url="http://decision",
        use_mock_tools=True,
    )


@pytest.fixture
def make_client(settings, decision_http):
    def build(agent_settings: Settings | None = None, *, decision=None, tools=None):
        app = create_app(
            agent_settings or settings, decision_http=decision or decision_http, tools=tools
        )
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")

    return build


@pytest.fixture
def client(make_client):
    return make_client()
