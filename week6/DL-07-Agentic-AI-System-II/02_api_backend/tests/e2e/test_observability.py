"""End-to-end checks of step 5.10: /ready, /metrics, service status and tracing.

The worker metrics and the service-status cache are reached through `docker compose
exec`. The trace check needs the stack started with tracing on:

    OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318 \\
        docker compose --profile observability up -d --wait
    E2E_JAEGER_URL=http://localhost:16686 ...
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from tests.e2e.test_data_protection import compose, needs_docker
from tests.e2e.test_recommendation_flow import BASE_URL, URL, body, token

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not BASE_URL, reason="E2E_BASE_URL is not set"),
]

JAEGER_URL = os.environ.get("E2E_JAEGER_URL", "")
WORKER_METRICS = (
    "import urllib.request;"
    "print(urllib.request.urlopen('http://127.0.0.1:9101/metrics', timeout=5).read().decode())"
)


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        yield client


def recommend(api: httpx.Client, correlation_id: str | None = None) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {token()}",
        "Idempotency-Key": str(uuid4()),
        "X-Correlation-ID": correlation_id or str(uuid4()),
    }
    # A question skips the cache, so the worker really calls the Agent.
    return api.post(URL, json=body(), params={"mode": "sync"}, headers=headers)


def sample(text: str, prefix: str) -> float:
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    return sum(float(line.rsplit(" ", 1)[1]) for line in lines)


def test_ready_reports_each_dependency(api: httpx.Client) -> None:
    response = api.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok", "redis_cache": "ok", "agent": "ok"},
    }


@needs_docker
def test_service_status_follows_the_agent_reports(api: httpx.Client) -> None:
    assert recommend(api).status_code == 200
    # Drop the 30 s cache so the page is recomputed from the new report.
    compose("exec", "-T", "redis-cache", "redis-cli", "DEL", "tsa:dev:status:service")

    response = api.get("/v1/service-status", headers={"Accept-Language": "en"})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=30"
    body_ = response.json()
    assert body_["components"]["agent"] == "ok"
    assert body_["components"]["weather"] == "ok"
    assert "mock-agent" not in response.text


@needs_docker
def test_metrics_from_api_and_worker(api: httpx.Client) -> None:
    before = sample(
        compose("exec", "-T", "worker", "python", "-c", WORKER_METRICS),
        'jobs_total{status="succeeded"}',
    )
    assert recommend(api).status_code == 200

    api_text = api.get("/metrics").text
    worker_text = compose("exec", "-T", "worker", "python", "-c", WORKER_METRICS)

    assert 'route="/v1/travel/recommendations"' in api_text
    assert 'celery_queue_depth{queue="recommendations"}' in api_text
    assert sample(worker_text, 'jobs_total{status="succeeded"}') == before + 1
    assert sample(worker_text, 'agent_request_duration_seconds_count{outcome="success"}') >= 1
    assert "recommendations_total{" in worker_text


def _find_trace(correlation_id: str) -> dict[str, Any] | None:
    tags = json.dumps({"app.correlation_id": correlation_id})
    response = httpx.get(
        f"{JAEGER_URL}/api/traces",
        params={"service": "travel-safety-api", "tags": tags, "limit": 5, "lookback": "1h"},
        timeout=10,
    )
    traces: list[dict[str, Any]] = response.json().get("data") or []
    return traces[0] if traces else None


@pytest.mark.skipif(not JAEGER_URL, reason="E2E_JAEGER_URL is not set")
def test_one_trace_from_http_through_celery_to_the_agent(api: httpx.Client) -> None:
    correlation_id = f"e2e-trace-{uuid4().hex[:8]}"
    assert recommend(api, correlation_id).status_code == 200

    trace = None
    deadline = time.monotonic() + 30
    while trace is None and time.monotonic() < deadline:
        trace = _find_trace(correlation_id)
        if trace is None:
            time.sleep(1)
    assert trace is not None, "no trace with this correlation id"

    services = {p["serviceName"] for p in trace["processes"].values()}
    assert services >= {"travel-safety-api", "travel-safety-worker"}
    agent_calls = [
        s
        for s in trace["spans"]
        if any(
            t["key"] in {"http.url", "url.full"} and "/v1/agent/runs" in str(t["value"])
            for t in s["tags"]
        )
    ]
    assert agent_calls, "the Agent call is not in the trace"
    dumped = json.dumps(trace)
    assert "Idempotency-Key" not in dumped
    assert "Bearer" not in dumped
