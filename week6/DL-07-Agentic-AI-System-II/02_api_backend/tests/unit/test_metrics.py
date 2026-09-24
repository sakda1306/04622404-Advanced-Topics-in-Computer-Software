from __future__ import annotations

from pathlib import Path

import pytest
from fakeredis import FakeAsyncRedis
from prometheus_client import REGISTRY

from app.core import metrics
from app.infrastructure.health import queue_depth


def test_render_adds_queue_depth_read_at_scrape_time() -> None:
    text = metrics.render({"recommendations": 3, "alerts": 0}).decode()

    assert 'celery_queue_depth{queue="recommendations"} 3.0' in text
    assert 'celery_queue_depth{queue="alerts"} 0.0' in text
    assert "# TYPE http_requests_total counter" in text


def test_render_without_queue_depth() -> None:
    assert "celery_queue_depth" not in metrics.render().decode()


def test_single_process_uses_the_default_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(metrics.MULTIPROC_ENV, raising=False)

    assert metrics.collecting_registry() is REGISTRY


def test_reset_empties_the_multiprocess_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "prom"
    directory.mkdir()
    (directory / "counter_1.db").write_bytes(b"old")
    monkeypatch.setenv(metrics.MULTIPROC_ENV, str(directory))

    metrics.reset_multiprocess_dir()

    assert directory.is_dir()
    assert list(directory.iterdir()) == []


def test_labels_for_optional_values() -> None:
    before = REGISTRY.get_sample_value(
        "recommendations_total",
        {"status": "failed", "risk_level": "none", "recommendation_type": "none"},
    )

    metrics.count_recommendation("failed", None, None)

    after = REGISTRY.get_sample_value(
        "recommendations_total",
        {"status": "failed", "risk_level": "none", "recommendation_type": "none"},
    )
    assert after == (before or 0) + 1


async def test_queue_depth_counts_every_priority_list(redis: FakeAsyncRedis) -> None:
    await redis.rpush("recommendations", "a", "b")  # type: ignore[misc]
    await redis.rpush("recommendations\x06\x163", "c")  # type: ignore[misc]
    await redis.rpush("maintenance", "d")  # type: ignore[misc]

    depth = await queue_depth(redis, ["recommendations", "alerts", "maintenance"])

    assert depth == {"recommendations": 3, "alerts": 0, "maintenance": 1}
