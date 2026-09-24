"""End-to-end checks for trips, live-alert scans, feedback and the review queue.

Runs like tests/e2e/test_recommendation_flow.py. The alert scan is started with
`docker compose exec worker celery call ...`, so that test also needs the docker CLI.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from tests.e2e.test_recommendation_flow import BASE_URL, body, post, token

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not BASE_URL, reason="E2E_BASE_URL is not set"),
]

PROJECT = Path(__file__).resolve().parents[2]
DOCKER = shutil.which("docker")


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        yield client


def trip_body(hours_ahead: int = 48) -> dict[str, Any]:
    return {
        "name": "E2E north",
        "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
        "destination": {"lat": 18.7883, "lon": 98.9853, "name": "Chiang Mai"},
        "departure_time": (datetime.now(UTC) + timedelta(hours=hours_ahead)).isoformat(),
        "timezone": "Asia/Bangkok",
        "alerts": {"enabled": True, "consent_at": datetime.now(UTC).isoformat()},
    }


def write(jwt: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt}", "Idempotency-Key": str(uuid4())}


def test_trip_lifecycle(api: httpx.Client) -> None:
    jwt = token()
    auth = {"Authorization": f"Bearer {jwt}"}

    created = api.post("/v1/trips", json=trip_body(), headers=write(jwt))
    assert created.status_code == 201, created.text
    url = created.headers["Location"]
    assessed = api.post(f"{url}/assessments", json={"language": "en"}, headers=write(jwt))
    assert assessed.status_code == 200, assessed.text

    trip = api.get(url, headers=auth).json()
    assert trip["last_assessment"]["recommendation_id"] == assessed.json()["recommendation_id"]
    later = (datetime.now(UTC) + timedelta(hours=50)).isoformat()
    moved = api.patch(
        url,
        content=f'{{"departure_time": "{later}"}}',
        headers={**auth, "Content-Type": "application/merge-patch+json"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["last_assessment"]["outdated"] is True
    history = api.get(f"{url}/assessments", headers=auth).json()["items"]
    assert [h["recommendation_id"] for h in history] == [assessed.json()["recommendation_id"]]
    assert api.delete(url, headers=auth).status_code == 204


@pytest.mark.skipif(DOCKER is None, reason="docker CLI is not available")
def test_alert_scan_reassesses_a_trip(api: httpx.Client) -> None:
    jwt = token()
    auth = {"Authorization": f"Bearer {jwt}"}
    created = api.post("/v1/trips", json=trip_body(hours_ahead=3), headers=write(jwt))
    assert created.status_code == 201, created.text
    url = created.headers["Location"]

    assert DOCKER is not None
    subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [
            DOCKER, "compose", "exec", "-T", "worker",
            "celery", "-A", "app.workers.celery_app:celery_app", "call",
            "app.workers.tasks.trip_alerts.scan_trip_alerts", "--queue", "alerts",
        ],
        cwd=PROJECT,
        check=True,
        capture_output=True,
        timeout=60,
    )  # fmt: skip

    deadline = time.monotonic() + 30
    trip: dict[str, Any] = {}
    while time.monotonic() < deadline:
        trip = api.get(url, headers=auth).json()
        if trip["last_assessment"] is not None:
            break
        time.sleep(0.5)
    assert trip["last_assessment"] is not None, trip
    history = api.get(f"{url}/assessments", headers=auth).json()["items"]
    assert len(history) == 1
    api.delete(url, headers=auth)


def test_unsafe_report_is_reviewed(api: httpx.Client) -> None:
    jwt = token()
    recommendation = post(api, jwt, body(question=None), mode="sync")
    assert recommendation.status_code == 200, recommendation.text
    rec_id = recommendation.json()["recommendation_id"]

    reported = api.post(
        f"/v1/recommendations/{rec_id}/feedback",
        json={"rating": 1, "report_type": "UNSAFE_ADVICE", "comment": "Road was closed"},
        headers=write(jwt),
    )
    assert reported.status_code == 201, reported.text
    assert reported.json()["review_status"] == "pending"
    feedback_id = reported.json()["feedback_id"]

    user_view = api.get("/v1/admin/feedback/reviews", headers={"Authorization": f"Bearer {jwt}"})
    assert user_view.status_code == 403

    reviewer = {"Authorization": f"Bearer {token('safety:review')}"}
    found: dict[str, Any] | None = None
    cursor: str | None = None
    while found is None:
        params = {"limit": "50", **({"cursor": cursor} if cursor else {})}
        page = api.get("/v1/admin/feedback/reviews", params=params, headers=reviewer).json()
        found = next((i for i in page["items"] if i["feedback_id"] == feedback_id), None)
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert found is not None
    # The reviewer sees the sanitized advice that was reported.
    assert found["recommendation"]["risk"]["level"] in {"LOW", "MEDIUM", "HIGH"}

    approved = api.patch(
        f"/v1/admin/feedback/reviews/{feedback_id}",
        json={"status": "approved", "note": "Confirmed"},
        headers=reviewer,
    )
    again = api.patch(
        f"/v1/admin/feedback/reviews/{feedback_id}", json={"status": "rejected"}, headers=reviewer
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["review_status"] == "approved"
    assert again.status_code == 409
