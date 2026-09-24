"""End-to-end checks for job cancel, the profile and account deletion (step 5.9a)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import AuthSettings
from app.core.security import issue_dev_token
from tests.e2e.test_recommendation_flow import BASE_URL, ISSUER, SIGNING_KEY, body, post

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not BASE_URL, reason="E2E_BASE_URL is not set"),
]

ALL = "travel:read travel:write profile:read profile:write"


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        yield client


def token(subject: str, scopes: str = ALL) -> str:
    settings = AuthSettings(
        jwt_issuer=ISSUER,
        jwt_audience="travel-safety-api",
        dev_jwt_signing_key=SecretStr(SIGNING_KEY),
    )
    return issue_dev_token(settings, subject=subject, scopes=scopes.split())


def test_cancel_a_slow_job(api: httpx.Client, scenario: Any) -> None:
    scenario("slow_20s")
    jwt = token(f"e2e-{uuid4()}")
    auth = {"Authorization": f"Bearer {jwt}"}

    accepted = post(api, jwt, body(question=None), mode="async")
    assert accepted.status_code == 202, accepted.text
    job = accepted.json()
    time.sleep(1.5)  # let the worker start the Agent call

    cancelled = api.delete(job["status_url"], headers=auth)
    again = api.delete(job["status_url"], headers=auth)
    with api.stream("GET", job["events_url"], headers=auth, timeout=10) as stream:
        text = "".join(stream.iter_text())

    assert cancelled.status_code == 202, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert again.status_code == 409
    assert "event: cancelled" in text
    assert "event: completed" not in text
    rec = api.get(f"/v1/travel/recommendations/{job['recommendation_id']}", headers=auth).json()
    assert rec["status"] == "cancelled"


def test_profile_and_consents(api: httpx.Client) -> None:
    auth = {"Authorization": f"Bearer {token(f'e2e-{uuid4()}')}"}

    patched = api.patch(
        "/v1/me",
        content=b'{"display_name": "E2E", "consents": {"analytics": true}}',
        headers={**auth, "Content-Type": "application/merge-patch+json"},
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["consents"] == {"live_alerts": False, "analytics": True}
    assert api.get("/v1/me", headers=auth).json()["display_name"] == "E2E"


def test_account_deletion(api: httpx.Client) -> None:
    auth = {"Authorization": f"Bearer {token(f'e2e-{uuid4()}')}"}
    first = api.get("/v1/me", headers=auth).json()

    deleted = api.delete("/v1/me", headers=auth)
    assert deleted.status_code == 202
    assert api.get("/v1/me", headers=auth).status_code in (200, 403)

    # The worker deletes the rows; the same login then gets a new, empty account.
    deadline = time.monotonic() + 30
    current: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = api.get("/v1/me", headers=auth)
        if response.status_code == 200 and response.json()["user_id"] != first["user_id"]:
            current = response.json()
            break
        time.sleep(0.5)
    assert current, "the account was not deleted in time"
    assert current["display_name"] is None
