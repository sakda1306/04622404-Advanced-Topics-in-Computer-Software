from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import AppEnv, Settings, get_settings


def test_loads_required_env_and_proposed_defaults() -> None:
    settings = Settings()

    assert settings.app.app_env is AppEnv.TEST
    assert settings.app.cors_allowed_origins == ["http://localhost:3000"]
    assert settings.auth.jwt_audience == "travel-safety-api"
    # A few proposed values from the Tunable Parameters table.
    assert settings.agent.sync_agent_timeout_seconds == 8.0  # P-02
    assert settings.limits.rate_limit_recommend == 10  # P-32
    assert settings.retention.retention_feedback_days == 180  # P-23
    assert settings.jobs.idempotency_ttl_seconds == 86400  # P-25


def test_tunable_value_can_be_overridden_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNC_AGENT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("RETENTION_FEEDBACK_DAYS", "90")

    settings = Settings()

    assert settings.agent.sync_agent_timeout_seconds == 5.0
    assert settings.retention.retention_feedback_days == 90


def test_cors_origins_are_split_and_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", " http://a.test , https://b.test ,")

    assert Settings().app.cors_allowed_origins == ["http://a.test", "https://b.test"]


def test_wildcard_cors_origin_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ValidationError, match="wildcard"):
        Settings()


@pytest.mark.parametrize(
    "missing",
    ["DATABASE_URL", "REDIS_URL", "JWT_ISSUER", "JWT_AUDIENCE", "AGENT_SERVICE_URL"],
)
def test_missing_required_env_fails_fast(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    monkeypatch.delenv(missing)

    with pytest.raises(ValidationError):
        Settings()


def test_invalid_number_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_USER", "0")

    with pytest.raises(ValidationError):
        Settings()


def test_log_level_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")

    assert Settings().observability.log_level == "DEBUG"


def test_empty_otel_endpoint_disables_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    assert Settings().observability.otel_exporter_otlp_endpoint is None


def test_dev_signing_key_is_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DEV_JWT_SIGNING_KEY", "local-only")

    with pytest.raises(ValidationError, match="DEV_JWT_SIGNING_KEY"):
        Settings()


def test_secrets_are_not_exposed_in_repr() -> None:
    settings = Settings()

    assert "tsa:tsa" not in repr(settings)
    assert "tsa:tsa" in settings.db.database_url.get_secret_value()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_safety_settings_defaults_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings().safety.low_confidence_threshold == 0.5  # P-51
    assert Settings().limits.min_route_distance_meters == 50  # P-52

    monkeypatch.setenv("LOW_CONFIDENCE_THRESHOLD", "1.5")
    with pytest.raises(ValidationError):
        Settings()


def test_stream_settings_defaults_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings().jobs.sse_max_stream_seconds == 300  # P-53
    assert Settings().jobs.stream_ticket_seconds == 60  # P-54

    monkeypatch.setenv("SSE_MAX_STREAM_SECONDS", "30")
    monkeypatch.setenv("STREAM_TICKET_SECONDS", "0")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("STREAM_TICKET_SECONDS", "10")
    assert Settings().jobs.sse_max_stream_seconds == 30


def test_trip_settings_defaults_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    trips = Settings().trips
    assert trips.max_trip_days_ahead == 90  # P-55
    assert trips.trip_alert_scan_minutes == 15  # P-56
    assert trips.trip_alert_window_hours == 24  # P-57
    assert trips.trip_alert_reassess_minutes == 60  # P-58
    assert trips.trip_alert_batch_size == 100  # P-59

    monkeypatch.setenv("TRIP_ALERT_SCAN_MINUTES", "5")
    monkeypatch.setenv("MAX_TRIP_DAYS_AHEAD", "30")
    assert Settings().trips.trip_alert_scan_minutes == 5
    assert Settings().trips.max_trip_days_ahead == 30
    monkeypatch.setenv("TRIP_ALERT_BATCH_SIZE", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_maintenance_settings_defaults_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings().maintenance.reaper_interval_minutes == 5  # P-60
    assert Settings().maintenance.account_deletion_retry_minutes == 10  # P-61

    monkeypatch.setenv("REAPER_INTERVAL_MINUTES", "2")
    assert Settings().maintenance.reaper_interval_minutes == 2
    monkeypatch.setenv("ACCOUNT_DELETION_RETRY_MINUTES", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_retention_and_storage_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    assert settings.retention.data_export_url_seconds == 900  # P-62
    assert settings.retention.data_export_cooldown_hours == 24  # P-63
    assert settings.storage.enabled is False

    monkeypatch.setenv("OBJECT_STORAGE_ENDPOINT", "minio:9000")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY", "tsa")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_KEY", "secret-secret")
    assert Settings().storage.enabled is True

    monkeypatch.setenv("PURGE_CRON", "every night")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("PURGE_CRON", "0 3 * * *")
    monkeypatch.setenv("PURGE_TIMEZONE", "Mars/Base")
    with pytest.raises(ValidationError):
        Settings()


def test_observability_settings_defaults_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    obs = Settings().observability
    assert "10.0.0.0/8" in obs.ops_allowed_networks
    assert (obs.service_status_window_minutes, obs.service_status_cache_seconds) == (15, 30)
    assert (obs.ready_agent_cache_seconds, obs.worker_metrics_port) == (10, 0)

    monkeypatch.setenv("OPS_ALLOWED_NETWORKS", " 10.1.0.0/16 , fd00::/8 ")
    monkeypatch.setenv("SERVICE_STATUS_WINDOW_MINUTES", "5")

    obs = Settings().observability
    assert obs.ops_allowed_networks == ["10.1.0.0/16", "fd00::/8"]
    assert obs.service_status_window_minutes == 5


def test_bad_ops_network_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPS_ALLOWED_NETWORKS", "10.0.0.0/8,not-a-network")

    with pytest.raises(ValidationError, match="not-a-network"):
        Settings()
