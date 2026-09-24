from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from app.api.resources import AppResources
from app.core.config import ObservabilitySettings, Settings
from app.core.logging import configure_logging
from app.core.telemetry import (
    CORRELATION_ATTRIBUTE,
    scrub_span,
    setup_tracing,
    shutdown_tracing,
)
from app.main import create_app


def span(**changes: Any) -> ReadableSpan:
    values: dict[str, Any] = {
        "name": "GET /v1/jobs/{job_id}/events",
        "attributes": {
            "http.url": "http://api/v1/jobs/1/events?ticket=secret-ticket",
            "http.target": "/v1/jobs/1/events?ticket=secret-ticket",
            "url.query": "ticket=secret-ticket",
            "net.peer.ip": "198.51.100.7",
            "client.address": "198.51.100.7",
            "http.status_code": 500,
        },
        "events": [
            Event(
                "exception",
                {
                    "exception.type": "IntegrityError",
                    "exception.message": "Key (email)=(someone@example.com) already exists",
                    "exception.stacktrace": "... someone@example.com ...",
                },
            )
        ],
        "status": Status(StatusCode.ERROR, "Key (email)=(someone@example.com)"),
    }
    values.update(changes)
    return ReadableSpan(**values)


def test_scrub_removes_queries_addresses_and_error_text() -> None:
    cleaned = scrub_span(span())

    text = json.dumps(dict(cleaned.attributes or {})) + repr(cleaned.events[0].attributes)
    assert "secret-ticket" not in text
    assert "198.51.100.7" not in text
    assert "someone@example.com" not in text
    assert cleaned.attributes is not None
    assert cleaned.attributes["http.url"] == "http://api/v1/jobs/1/events"
    assert cleaned.attributes["http.status_code"] == 500
    assert dict(cleaned.events[0].attributes or {}) == {"exception.type": "IntegrityError"}
    assert cleaned.status.status_code is StatusCode.ERROR
    assert cleaned.status.description is None


@pytest.fixture
def exporter() -> Iterator[InMemorySpanExporter]:
    memory = InMemorySpanExporter()
    setup_tracing(ObservabilitySettings(otel_service_name="tsa-test"), exporter=memory)
    try:
        yield memory
    finally:
        shutdown_tracing()


async def test_request_spans_are_scrubbed_and_carry_the_correlation_id(
    exporter: InMemorySpanExporter, settings: Settings, resources: AppResources
) -> None:
    app = create_app(settings, resources)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await client.get("/health")
        await client.get(
            "/v1/jobs/0192f3c0-0000-7000-8000-000000000001/events?ticket=secret-ticket",
            headers={"X-Correlation-ID": "corr-trace-1"},
        )

    spans = exporter.get_finished_spans()
    assert spans, "the request produced no span"
    assert all("/health" not in s.name for s in spans)  # probes are not traced
    server = [s for s in spans if s.kind is trace.SpanKind.SERVER]
    assert len(server) == 1
    assert server[0].attributes is not None
    assert server[0].attributes[CORRELATION_ATTRIBUTE] == "corr-trace-1"
    dumped = " ".join(json.dumps(dict(s.attributes or {})) for s in spans)
    assert "secret-ticket" not in dumped
    assert "127.0.0.1" not in dumped


def test_logs_carry_the_trace_id(
    exporter: InMemorySpanExporter, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(json_output=True)
    tracer = trace.get_tracer("test")

    with tracer.start_as_current_span("work") as current:
        structlog.get_logger("test").info("inside_span")
        expected = format(current.get_span_context().trace_id, "032x")

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["trace_id"] == expected
    assert len(line["span_id"]) == 16


def test_tracing_is_off_without_an_endpoint() -> None:
    assert setup_tracing(ObservabilitySettings()) is None
