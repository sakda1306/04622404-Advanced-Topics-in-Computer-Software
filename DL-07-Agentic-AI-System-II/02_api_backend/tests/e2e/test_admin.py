"""End-to-end checks of step 5.11: admin tools and the training data export."""

from __future__ import annotations

import gzip
import json
import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import AuthSettings
from app.core.security import issue_dev_token
from tests.e2e.test_recommendation_flow import BASE_URL, ISSUER, SIGNING_KEY, URL, body

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not BASE_URL, reason="E2E_BASE_URL is not set"),
]


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        yield client


def headers(subject: str, scopes: str, **extra: str) -> dict[str, str]:
    settings = AuthSettings(
        jwt_issuer=ISSUER,
        jwt_audience="travel-safety-api",
        dev_jwt_signing_key=SecretStr(SIGNING_KEY),
    )
    jwt = issue_dev_token(settings, subject=subject, scopes=scopes.split())
    return {"Authorization": f"Bearer {jwt}", **extra}


def recommend(api: httpx.Client, subject: str) -> dict[str, Any]:
    response = api.post(
        URL,
        json=body(question=f"e2e admin {uuid4().hex[:6]}"),
        params={"mode": "sync"},
        headers=headers(subject, "travel:read travel:write", **{"Idempotency-Key": str(uuid4())}),
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def test_recommendation_diagnostics_and_job_listing(api: httpx.Client) -> None:
    rec = recommend(api, f"e2e-{uuid4()}")
    admin = headers(f"e2e-admin-{uuid4()}", "admin:read")

    detail = api.get(f"/v1/admin/recommendations/{rec['recommendation_id']}", headers=admin)
    jobs = api.get("/v1/admin/jobs", params={"limit": 50}, headers=admin)

    assert detail.status_code == 200, detail.text
    data = detail.json()
    assert data["agent_runs"][0]["status"] == "success"
    assert data["versions"]["api"]
    assert "Chiang Mai" not in detail.text
    assert "13.7563" not in detail.text
    assert jobs.status_code == 200
    assert data["job"]["job_id"] in {j["job_id"] for j in jobs.json()["items"]}


def test_refused_admin_calls_are_in_the_audit_log(api: httpx.Client) -> None:
    intruder = f"e2e-intruder-{uuid4()}"

    refused = api.get("/v1/admin/jobs", headers=headers(intruder, "travel:read"))
    logs = api.get(
        "/v1/admin/audit-logs",
        params={"action": "admin.jobs_list", "result": "denied"},
        headers=headers(f"e2e-admin-{uuid4()}", "admin:read"),
    )

    assert refused.status_code == 403
    assert logs.status_code == 200
    mine = [row for row in logs.json()["items"] if row["actor_ref"] == intruder]
    assert len(mine) == 1
    assert mine[0]["metadata"] == {"required_scope": "admin:read"}


def test_training_export_downloads_anonymized_rows(api: httpx.Client) -> None:
    subject = f"e2e-{uuid4()}"
    consent = api.patch(
        "/v1/me",
        json={"consents": {"analytics": True}},
        headers=headers(subject, "profile:read profile:write"),
    )
    assert consent.status_code == 200, consent.text
    rec = recommend(api, subject)
    admin = headers(f"e2e-admin-{uuid4()}", "admin:write")

    accepted = api.post(
        "/v1/admin/exports/training-data",
        json={},
        headers={**admin, "Idempotency-Key": str(uuid4())},
    )
    assert accepted.status_code == 202, accepted.text

    deadline = time.monotonic() + 30
    status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status = api.get(accepted.headers["Location"], headers=admin).json()
        if status["status"] in ("ready", "failed"):
            break
        time.sleep(0.5)
    assert status["status"] == "ready", status
    assert status["row_count"] >= 1
    download = httpx.get(status["download_url"], timeout=10)
    assert download.status_code == 200
    text = gzip.decompress(download.content).decode()
    lines = [json.loads(line) for line in text.splitlines()]
    assert len(lines) == status["row_count"]
    assert {"origin_geohash", "risk_level", "feedback", "versions"} <= set(lines[-1])
    assert rec["recommendation_id"] not in text
    assert subject not in text
    assert "13.7563" not in text
