"""OpenTelemetry tracing: HTTP -> Celery -> Agent in one trace (NFR-06).

Tracing is off unless OTEL_EXPORTER_OTLP_ENDPOINT is set. Spans pass through
`ScrubbingExporter` before they leave the process: query strings, client addresses,
error messages and exception text are removed there, in one place (D-89), because
instrumentation libraries add them without asking.
"""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Status

from app.core.config import ObservabilitySettings

# Spans for these paths are noise: probes and scrapes run every few seconds.
EXCLUDED_URLS = "/health,/ready,/metrics"
CORRELATION_ATTRIBUTE = "app.correlation_id"
TRACES_PATH = "/v1/traces"

_URL_KEYS = frozenset({"http.url", "url.full", "http.target"})
_DROPPED_KEYS = frozenset(
    {
        "url.query",
        "net.peer.ip",
        "net.sock.peer.addr",
        "http.client_ip",
        "client.address",
        "network.peer.address",
    }
)
_KEPT_EXCEPTION_KEYS = frozenset({"exception.type"})

_provider: TracerProvider | None = None


def _without_query(value: object) -> object:
    if isinstance(value, str):
        return value.split("?", 1)[0].split("#", 1)[0]
    return value


def scrub_attributes(attributes: Any) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        if key in _DROPPED_KEYS:
            continue
        cleaned[key] = _without_query(value) if key in _URL_KEYS else value
    return cleaned


def _scrub_event(event: Event) -> Event:
    if event.name != "exception":
        return Event(event.name, scrub_attributes(event.attributes), event.timestamp)
    # Exception messages can quote SQL values or user text; the type is enough to search.
    kept = {k: v for k, v in (event.attributes or {}).items() if k in _KEPT_EXCEPTION_KEYS}
    return Event(event.name, kept, event.timestamp)


def scrub_span(span: ReadableSpan) -> ReadableSpan:
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=scrub_attributes(span.attributes),
        events=[_scrub_event(event) for event in span.events],
        links=span.links,
        kind=span.kind,
        # Keep the error flag, drop the description (it is the exception text).
        status=Status(span.status.status_code),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class ScrubbingExporter(SpanExporter):
    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([scrub_span(span) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def _otlp_exporter(endpoint: str) -> SpanExporter:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    base = endpoint.rstrip("/")
    url = base if base.endswith(TRACES_PATH) else base + TRACES_PATH
    return OTLPSpanExporter(endpoint=url)


def setup_tracing(
    settings: ObservabilitySettings, *, exporter: SpanExporter | None = None
) -> TracerProvider | None:
    """Create the provider and instrument libraries once per process.

    Tests pass an in-memory `exporter`; it is exported synchronously.
    """
    global _provider
    if _provider is not None:
        return _provider
    endpoint = settings.otel_exporter_otlp_endpoint
    if exporter is None and endpoint is None:
        return None

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: settings.otel_service_name}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(ScrubbingExporter(exporter)))
    else:
        assert endpoint is not None
        provider.add_span_processor(BatchSpanProcessor(ScrubbingExporter(_otlp_exporter(endpoint))))
    trace.set_tracer_provider(provider)

    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    # Redis spans carry the command name only; arguments are replaced with "?".
    RedisInstrumentor().instrument(tracer_provider=provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    CeleryInstrumentor().instrument(tracer_provider=provider)  # type: ignore[no-untyped-call]
    _provider = provider
    return provider


def shutdown_tracing() -> None:
    """Flush and undo the instrumentation (process exit and tests)."""
    global _provider
    if _provider is None:
        return
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    celery = CeleryInstrumentor()  # type: ignore[no-untyped-call]
    for instrumentor in (RedisInstrumentor(), HTTPXClientInstrumentor(), celery):
        instrumentor.uninstrument()
    _provider.shutdown()
    _provider = None


def instrument_app(app: Any) -> None:
    if _provider is None:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=_provider,
        excluded_urls=EXCLUDED_URLS,
        # One span per request; no extra span for every SSE chunk.
        exclude_spans=["receive", "send"],
    )


def instrument_engine(engine: Any) -> None:
    """Trace SQL statements (bound values are never part of the statement text)."""
    if _provider is None:
        return
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(
        engine=getattr(engine, "sync_engine", engine), tracer_provider=_provider
    )


def tag_correlation(correlation_id: str) -> None:
    """Put the correlation id on the current span so traces and logs can be joined."""
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute(CORRELATION_ATTRIBUTE, correlation_id)


def add_trace_ids(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: add trace_id and span_id while a span is active."""
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event_dict.setdefault("trace_id", format(context.trace_id, "032x"))
        event_dict.setdefault("span_id", format(context.span_id, "016x"))
    return event_dict
