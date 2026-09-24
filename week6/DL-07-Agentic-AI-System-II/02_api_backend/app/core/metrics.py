"""Prometheus metrics (docs/02_api_spec.md section 10).

Labels only take values from small fixed sets (route templates, enum values, rule ids),
never ids, paths with ids, or anything a user typed.

Processes that fork (uvicorn --workers, the Celery prefork pool) share their numbers
through files in PROMETHEUS_MULTIPROC_DIR (D-91). The variable must be set before this
module is imported, which is why it comes from the container environment.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector

MULTIPROC_ENV = "PROMETHEUS_MULTIPROC_DIR"
CONTENT_TYPE = CONTENT_TYPE_LATEST
NONE_LABEL = "none"

# In multiprocess mode, metrics without labels open their file right here at import.
if _shared_dir := os.environ.get(MULTIPROC_ENV):
    Path(_shared_dir).mkdir(parents=True, exist_ok=True)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests by route template, method and status code",
    ["route", "method", "status"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["route", "method"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
AGENT_DURATION = Histogram(
    "agent_request_duration_seconds",
    "Duration of one call to the Agent, by outcome",
    ["outcome"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30, 60),
)
AGENT_ERRORS = Counter(
    "agent_errors_total",
    "Agent calls that ended in an error, after retries",
    ["code"],
)
JOBS = Counter("jobs_total", "Jobs that reached a final status", ["status"])
RECOMMENDATIONS = Counter(
    "recommendations_total",
    "Recommendations stored",
    ["status", "risk_level", "recommendation_type"],
)
CACHE_HITS = Counter("cache_hits_total", "Recommendation cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Recommendation cache misses")
RATE_LIMIT_HITS = Counter("rate_limit_hits_total", "Requests refused by a rate limit", ["scope"])
SAFETY_OVERRIDES = Counter(
    "safety_gate_overrides_total",
    "Answers the Safety Gate changed, by rule",
    ["rule"],
)
SAFETY_REJECTIONS = Counter(
    "safety_gate_rejections_total",
    "Agent answers the Safety Gate refused, by rule",
    ["rule"],
)
SAFETY_REVIEWS = Counter(
    "safety_review_requested_total",
    "Feedback reports sent to the safety review queue (D-68)",
    ["report_type"],
)


def label(value: object) -> str:
    """Enum value or `none`, for optional labels."""
    if value is None:
        return NONE_LABEL
    return str(getattr(value, "value", value))


def count_recommendation(status: object, risk_level: object, recommendation_type: object) -> None:
    RECOMMENDATIONS.labels(
        status=label(status),
        risk_level=label(risk_level),
        recommendation_type=label(recommendation_type),
    ).inc()


def multiprocess_dir() -> str | None:
    return os.environ.get(MULTIPROC_ENV) or None


def reset_multiprocess_dir() -> None:
    """Empty the shared directory; call once in the parent before processes start."""
    directory = multiprocess_dir()
    if directory is None:
        return
    path = Path(directory)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def mark_process_dead(pid: int) -> None:
    if multiprocess_dir() is not None:
        multiprocess.mark_process_dead(pid)  # type: ignore[no-untyped-call]


def collecting_registry() -> CollectorRegistry:
    """The registry to scrape: all processes' files, or this process alone."""
    if multiprocess_dir() is None:
        return REGISTRY
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
    return registry


class _QueueDepth(Collector):
    """Values read at scrape time. A Gauge object would write multiprocess files."""

    def __init__(self, depth: Mapping[str, int]) -> None:
        self._depth = depth

    def collect(self) -> Iterable[Metric]:
        family = GaugeMetricFamily(
            "celery_queue_depth", "Messages waiting in each Celery queue", labels=["queue"]
        )
        for queue, depth in self._depth.items():
            family.add_metric([queue], depth)
        yield family


def render(queue_depth: Mapping[str, int] | None = None) -> bytes:
    """Prometheus text for this service, plus values read at scrape time."""
    output = generate_latest(collecting_registry())
    if queue_depth is not None:
        live = CollectorRegistry()
        live.register(_QueueDepth(queue_depth))
        output += generate_latest(live)
    return output
