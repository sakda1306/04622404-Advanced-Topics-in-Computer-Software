"""End-to-end checks against the running compose stack (api, worker, mock-agent).

    docker compose up -d --build --wait
    E2E_BASE_URL=http://localhost:8000 E2E_MOCK_AGENT_URL=http://localhost:8010 \
        uv run pytest -m e2e tests/e2e

Skipped unless E2E_BASE_URL is set.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import AuthSettings
from app.core.security import issue_dev_token

BASE_URL = os.environ.get("E2E_BASE_URL", "")
MOCK_URL = os.environ.get("E2E_MOCK_AGENT_URL", "http://localhost:8010")
# The compose default; override when the stack uses another key.
SIGNING_KEY = os.environ.get("E2E_DEV_JWT_SIGNING_KEY", "dev-only-signing-key-change-me-0123456789")
ISSUER = os.environ.get("E2E_JWT_ISSUER", "http://localhost:8000/dev-issuer")
URL = "/v1/travel/recommendations"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not BASE_URL, reason="E2E_BASE_URL is not set"),
]


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        yield client


def runs() -> int:
    count: int = httpx.get(f"{MOCK_URL}/_mock/scenario", timeout=5).json()["runs"]
    return count


def token(scopes: str = "travel:read travel:write") -> str:
    settings = AuthSettings(
        jwt_issuer=ISSUER,
        jwt_audience="travel-safety-api",
        dev_jwt_signing_key=SecretStr(SIGNING_KEY),
    )
    return issue_dev_token(settings, subject=f"e2e-{uuid4()}", scopes=scopes.split())


def body(question: str | None = "Is it safe to travel?") -> dict[str, Any]:
    return {
        "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
        "destination": {"lat": 18.7883, "lon": 98.9853, "name": "Chiang Mai"},
        "departure_time": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "timezone": "Asia/Bangkok",
        "language": "th",
        "question": question,
    }


def post(api: httpx.Client, jwt: str, payload: dict[str, Any], **params: str) -> httpx.Response:
    return api.post(
        URL,
        json=payload,
        params=params,
        headers={"Authorization": f"Bearer {jwt}", "Idempotency-Key": str(uuid4())},
    )


def test_low_risk_is_answered_synchronously(api: httpx.Client, scenario: Any) -> None:
    scenario("low_risk")

    response = post(api, token(), body())

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["recommendation"]["type"] == "TRAVEL_NORMALLY"
    assert data["disclaimer"].startswith("คำแนะนำนี้")


def test_disaster_outage_is_partial(api: httpx.Client, scenario: Any) -> None:
    scenario("partial_disaster_down")

    data = post(api, token(), body()).json()

    assert data["status"] == "partial_result"
    assert data["recommendation"]["type"] is None


def test_high_risk_has_emergency_instructions(api: httpx.Client, scenario: Any) -> None:
    scenario("high_risk")

    data = post(api, token(), body()).json()

    assert data["risk"]["level"] == "HIGH"
    assert data["emergency_instructions"]["contacts"]


def test_unavailable_agent_is_503(api: httpx.Client, scenario: Any) -> None:
    scenario("unavailable_503")

    response = post(api, token(), body())

    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert response.headers["Retry-After"]


def test_slow_agent_is_followed_over_sse(api: httpx.Client, scenario: Any) -> None:
    scenario("slow_20s")
    jwt = token()
    auth = {"Authorization": f"Bearer {jwt}"}

    accepted = post(api, jwt, body())
    assert accepted.status_code == 202, accepted.text
    job = accepted.json()
    ticket = api.post(f"{job['status_url']}/stream-ticket", headers=auth).json()["ticket"]

    events: list[str] = []
    started = time.monotonic()
    with api.stream("GET", job["events_url"], params={"ticket": ticket}, timeout=60) as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        for line in stream.iter_lines():
            if line.startswith("event: "):
                events.append(line.removeprefix("event: "))
            if line.startswith("data: ") and events and events[-1] == "completed":
                assert json.loads(line.removeprefix("data: "))["status"] == "completed"
                break
            assert time.monotonic() - started < 60

    assert events[0] == "progress"
    assert events[-1] == "completed"
    assert api.get(job["status_url"], headers=auth).json()["status"] == "succeeded"
    result = api.get(f"{URL}/{job['recommendation_id']}", headers=auth).json()
    assert result["recommendation"]["type"] == "DELAY_TRAVEL"


def test_same_idempotency_key_is_replayed(api: httpx.Client, scenario: Any) -> None:
    scenario("low_risk")
    jwt = token()
    headers = {"Authorization": f"Bearer {jwt}", "Idempotency-Key": str(uuid4())}
    payload = body()

    first = api.post(URL, json=payload, headers=headers)
    second = api.post(URL, json=payload, headers=headers)

    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json() == first.json()


def test_identical_request_without_question_uses_the_cache(
    api: httpx.Client, scenario: Any
) -> None:
    scenario("low_risk")
    jwt = token()
    payload = body(question=None)
    first = post(api, jwt, payload)
    before = runs()

    second = post(api, jwt, payload)

    assert second.status_code == 200
    assert runs() == before
    assert second.json()["recommendation_id"] != first.json()["recommendation_id"]


def test_conversation_with_follow_up(api: httpx.Client, scenario: Any) -> None:
    scenario("low_risk")
    jwt = token()
    auth = {"Authorization": f"Bearer {jwt}"}

    def write() -> dict[str, str]:
        return {**auth, "Idempotency-Key": str(uuid4())}

    created = api.post("/v1/conversations", json={"language": "th"}, headers=write())
    assert created.status_code == 201, created.text
    url = created.headers["Location"]
    trip = body()
    first = api.post(
        f"{url}/messages",
        json={
            "content": "ปลอดภัยไหม",
            "overrides": {
                k: trip[k] for k in ("origin", "destination", "departure_time", "timezone")
            },
        },
        headers=write(),
    )
    later = (datetime.now(UTC) + timedelta(days=2, hours=3)).isoformat()
    follow_up = api.post(
        f"{url}/messages",
        json={"content": "ถ้าออกช้ากว่าเดิม 3 ชั่วโมงล่ะ", "overrides": {"departure_time": later}},
        headers=write(),
    )

    assert first.status_code == 200, first.text
    assert follow_up.status_code == 200, follow_up.text
    messages = api.get(f"{url}/messages", headers=auth).json()["items"]
    assert [m["role"] for m in messages] == ["assistant", "user", "assistant", "user"]
    history = api.get(URL, headers=auth).json()["items"]
    assert history[0]["recommendation_id"] == follow_up.json()["recommendation_id"]
    assert api.delete(url, headers=auth).status_code == 204
    assert api.get(url, headers=auth).status_code == 404
