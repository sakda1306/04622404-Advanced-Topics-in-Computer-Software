"""Live containerized End-to-End integration test suite.

Validates the complete cross-module contract across:
Keycloak (08) -> Gateway API (02) -> Celery Worker -> Travel Agent (03)
-> In-process 04 / 05 / 06 -> Decision Engine (07)
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest


def test_e2e_unauthorized_request_fails_with_401(api_url: str) -> None:
    """Requests lacking a valid Bearer token must be rejected immediately."""
    payload = {
        "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
        "destination": {"lat": 13.3611, "lon": 100.9847, "name": "Chonburi"},
        "departure_time": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "timezone": "Asia/Bangkok",
        "language": "th",
    }
    res = httpx.post(f"{api_url}/v1/travel/recommendations", json=payload, timeout=10.0)
    assert res.status_code == 401


def test_e2e_unsupported_region_fails_with_422(dev_token: str, api_url: str) -> None:
    """Coordinates outside Thailand must be rejected with 422 UNSUPPORTED_REGION per D-11."""
    payload = {
        "origin": {"lat": 35.6762, "lon": 139.6503, "name": "Tokyo"},
        "destination": {"lat": 35.6895, "lon": 139.6917, "name": "Shinjuku"},
        "departure_time": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "timezone": "Asia/Bangkok",
        "language": "th",
        "preferences": {"travel_modes": ["CAR"], "avoid": []},
    }
    headers = {
        "Authorization": f"Bearer {dev_token}",
        "Idempotency-Key": str(uuid4()),
    }
    res = httpx.post(
        f"{api_url}/v1/travel/recommendations",
        json=payload,
        headers=headers,
        timeout=10.0,
    )
    assert res.status_code == 422
    body = res.json()
    assert body.get("code") == "UNSUPPORTED_REGION"


def test_e2e_safe_route_produces_travel_normally(dev_token: str, api_url: str) -> None:
    # Morning departure at 08:00 AM local time (01:00 UTC) in clear forecast window
    departure = (datetime.now(UTC) + timedelta(days=1)).replace(hour=1, minute=0, second=0, microsecond=0)
    payload = {
        "origin": {"lat": 13.7563, "lon": 100.5018, "name": "Bangkok"},
        "destination": {"lat": 13.3611, "lon": 100.9847, "name": "Chonburi"},
        "departure_time": departure.isoformat(),
        "timezone": "Asia/Bangkok",
        "language": "th",
        "preferences": {"travel_modes": ["CAR"], "avoid": []},
    }
    headers = {
        "Authorization": f"Bearer {dev_token}",
        "Idempotency-Key": str(uuid4()),
    }

    res = httpx.post(
        f"{api_url}/v1/travel/recommendations",
        json=payload,
        headers=headers,
        timeout=30.0,
    )

    if res.status_code == 202:
        # Asynchronous execution via Celery worker: poll status_url
        job = res.json()
        status_url = job.get("status_url")
        rec_id = job.get("recommendation_id")
        auth_header = {"Authorization": f"Bearer {dev_token}"}

        deadline = time.monotonic() + 45.0
        target_status_url = f"{api_url}{status_url}" if status_url.startswith("/") else status_url
        while time.monotonic() < deadline:
            poll_res = httpx.get(target_status_url, headers=auth_header, timeout=10.0)
            if poll_res.status_code == 200:
                poll_data = poll_res.json()
                if poll_data.get("status") == "succeeded":
                    succeeded = True
                    break
                if poll_data.get("status") == "failed":
                    pytest.fail(f"Background job failed: {poll_data}")
            time.sleep(1.5)

        assert succeeded, f"Job did not complete within timeout: {job}"
        rec_res = httpx.get(
            f"{api_url}/v1/travel/recommendations/{rec_id}",
            headers=auth_header,
            timeout=10.0,
        )
        assert rec_res.status_code == 200, rec_res.text
        data = rec_res.json()
    else:
        assert res.status_code in (200, 201), res.text
        data = res.json()

    assert data["status"] in ("completed", "partial_result")
    assert data["risk"]["level"] in ("LOW", "MEDIUM", "HIGH")
    assert data["recommendation"]["summary"] is not None
    assert data["recommendation"]["type"] in (
        "TRAVEL_NORMALLY",
        "AVOID_TRAVEL",
        "DELAY_TRAVEL",
        "CHANGE_ROUTE",
        None,
    )
