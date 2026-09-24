"""
Monitoring for 08_recommendation_feedback.

Per 03_process.txt, safety metrics and UX metrics must be measured
SEPARATELY. init_monitoring() is safe to call even before the
monitoring stack (Prometheus/Grafana) is deployed.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger("recommendation_feedback")

try:
    from prometheus_client import Counter, Histogram

    # --- Safety metrics (never gated by A/B tests) ---
    UNSAFE_RECOMMENDATION_RATE = Counter(
        "reco_unsafe_feedback_total",
        "Count of feedback submissions classified as UNSAFE.",
    )
    ALERT_LATENCY = Histogram(
        "reco_alert_latency_seconds",
        "Time from underlying event detection to alert delivery.",
    )

    # --- UX metrics (safe to A/B test against) ---
    RECOMMENDATION_VIEWED = Counter(
        "reco_viewed_total",
        "Count of recommendations viewed by users.",
        ["action_code"],
    )
    FEEDBACK_SUBMITTED = Counter(
        "reco_feedback_submitted_total",
        "Count of feedback submissions by category.",
        ["category"],
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed; metrics disabled")


def record_alert_latency(seconds: float) -> None:
    if _PROMETHEUS_AVAILABLE:
        ALERT_LATENCY.observe(seconds)
    logger.info("alert_latency", seconds=seconds)


def record_unsafe_feedback() -> None:
    if _PROMETHEUS_AVAILABLE:
        UNSAFE_RECOMMENDATION_RATE.inc()
    logger.warning("unsafe_feedback_recorded")


def record_recommendation_viewed(action_code: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        RECOMMENDATION_VIEWED.labels(action_code=action_code).inc()
    logger.info("recommendation_viewed", action_code=action_code)


def record_feedback_submitted(category: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        FEEDBACK_SUBMITTED.labels(category=category).inc()


def init_monitoring(service_name: str = "recommendation_feedback") -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )
    logger.info("monitoring_initialized", service=service_name, prometheus=_PROMETHEUS_AVAILABLE)
