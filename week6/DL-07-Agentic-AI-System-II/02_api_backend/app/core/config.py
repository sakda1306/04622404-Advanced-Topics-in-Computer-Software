"""Application settings.

Every tunable value from docs/02_api_spec.md section 2 (P-xx) lives here with its
proposed default, so it can be changed through environment variables only.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from ipaddress import ip_network
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ENV_CONFIG = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
# Loopback and private ranges: probes and Prometheus reach the pod from inside.
_PRIVATE_NETWORKS = (
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "::1/128",
    "fc00::/7",
)


class AppEnv(StrEnum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PROD = "prod"


class AppSettings(BaseSettings):
    model_config = _ENV_CONFIG

    app_env: AppEnv = AppEnv.DEV
    api_version: str = "1.0.0"
    enable_docs: bool = True
    cors_allowed_origins: Annotated[list[str], NoDecode]
    max_body_bytes: int = Field(default=64 * 1024, gt=0)  # P-44
    error_type_base_url: str = "https://errors.travel-safety.example/"
    # Proxies whose X-Forwarded-For is trusted for the client IP (rate limits use it).
    forwarded_allow_ips: str = "127.0.0.1"

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def _no_wildcard(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("wildcard origin is not allowed; list origins explicitly")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env in {AppEnv.STAGING, AppEnv.PROD}


class DatabaseSettings(BaseSettings):
    model_config = _ENV_CONFIG

    database_url: SecretStr
    db_pool_size: int = Field(default=10, gt=0)
    db_max_overflow: int = Field(default=10, ge=0)


class RedisSettings(BaseSettings):
    model_config = _ENV_CONFIG

    redis_url: SecretStr
    redis_cache_url: SecretStr | None = None  # empty -> REDIS_URL database /1 (D-14)
    celery_broker_url: SecretStr | None = None  # empty -> REDIS_URL database /2
    redis_socket_timeout_seconds: float = Field(default=2.0, gt=0)

    @field_validator("redis_cache_url", "celery_broker_url", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        return value or None

    def core_url(self) -> str:
        return self.redis_url.get_secret_value()

    def cache_url(self) -> str:
        if self.redis_cache_url is not None:
            return self.redis_cache_url.get_secret_value()
        return _with_redis_db(self.core_url(), 1)

    def broker_url(self) -> str:
        if self.celery_broker_url is not None:
            return self.celery_broker_url.get_secret_value()
        return _with_redis_db(self.core_url(), 2)


def _with_redis_db(url: str, db: int) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{db}"))


class AuthSettings(BaseSettings):
    model_config = _ENV_CONFIG

    jwt_issuer: str = Field(min_length=1)
    jwt_audience: str = Field(min_length=1)
    jwks_url: str | None = None
    jwks_cache_seconds: int = Field(default=600, gt=0)  # P-11
    jwks_min_refresh_seconds: int = Field(default=60, gt=0)
    jwt_algorithms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["RS256", "ES256"]
    )
    jwt_leeway_seconds: int = Field(default=30, ge=0)
    dev_jwt_signing_key: SecretStr | None = None

    @field_validator("jwks_url", "dev_jwt_signing_key", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        return value or None

    @field_validator("jwt_algorithms", mode="before")
    @classmethod
    def _split_algorithms(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("jwt_algorithms")
    @classmethod
    def _asymmetric_only(cls, value: list[str]) -> list[str]:
        # Shared-secret algorithms are only allowed through DEV_JWT_SIGNING_KEY.
        allowed = {"RS256", "RS384", "RS512", "PS256", "ES256", "ES384", "EdDSA"}
        unsupported = [alg for alg in value if alg not in allowed]
        if unsupported or not value:
            raise ValueError(f"unsupported JWT algorithms: {unsupported or value}")
        return value

    @field_validator("dev_jwt_signing_key")
    @classmethod
    def _dev_key_length(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("DEV_JWT_SIGNING_KEY must be at least 32 characters")
        return value


class AgentSettings(BaseSettings):
    model_config = _ENV_CONFIG

    agent_service_url: str = Field(min_length=1)
    # Service-to-service auth (spec 9.1): OAuth2 client credentials in production,
    # or a static shared token for development. Neither set -> no Authorization header.
    agent_token_url: str | None = None
    agent_audience: str = "travel-agent"
    agent_client_id: str | None = None
    agent_client_secret: SecretStr | None = None
    agent_service_token: SecretStr | None = None
    agent_retry_base_seconds: float = Field(default=0.5, gt=0)
    agent_max_tool_calls: int = Field(default=20, gt=0)
    agent_max_response_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    agent_cancel_timeout_seconds: float = Field(default=2.0, gt=0)
    agent_connect_timeout_seconds: float = Field(default=2.0, gt=0)  # P-06
    sync_agent_timeout_seconds: float = Field(default=8.0, gt=0)  # P-02
    job_agent_timeout_seconds: float = Field(default=60.0, gt=0)  # P-04
    agent_max_retries: int = Field(default=2, ge=0)  # P-07
    agent_cb_failure_threshold: int = Field(default=5, gt=0)  # P-08
    agent_cb_window_seconds: int = Field(default=30, gt=0)  # P-08
    agent_cb_reset_seconds: int = Field(default=30, gt=0)  # P-08
    agent_context_messages: int = Field(default=10, ge=0)  # P-45

    @field_validator(
        "agent_token_url",
        "agent_client_id",
        "agent_client_secret",
        "agent_service_token",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        return value or None

    @model_validator(mode="after")
    def _client_credentials_complete(self) -> AgentSettings:
        parts = (self.agent_token_url, self.agent_client_id, self.agent_client_secret)
        if any(parts) and not all(parts):
            raise ValueError(
                "AGENT_TOKEN_URL, AGENT_CLIENT_ID and AGENT_CLIENT_SECRET must be set together"
            )
        return self


class LimitSettings(BaseSettings):
    model_config = _ENV_CONFIG

    rate_limit_user: int = Field(default=60, gt=0)  # P-30, per minute
    rate_limit_ip: int = Field(default=120, gt=0)  # P-31, per minute
    rate_limit_recommend: int = Field(default=10, gt=0)  # P-32, per minute
    max_active_jobs_per_user: int = Field(default=3, gt=0)  # P-33
    max_streams_per_user: int = Field(default=3, gt=0)  # P-34
    sse_heartbeat_seconds: int = Field(default=15, gt=0)  # P-35
    max_page_size: int = Field(default=50, gt=0)  # P-40
    max_question_chars: int = Field(default=1000, gt=0)  # P-41
    max_waypoints: int = Field(default=5, ge=0)  # P-42
    max_days_ahead: int = Field(default=14, gt=0)  # P-43
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    min_route_distance_meters: float = Field(default=50.0, ge=0)  # P-52
    # Rate limiting protects capacity; an unavailable Redis should not take the API down.
    rate_limit_fail_open: bool = True


class AdminSettings(BaseSettings):
    model_config = _ENV_CONFIG

    admin_max_range_days: int = Field(default=31, gt=0)  # P-67: jobs / audit log listings
    training_export_ttl_days: int = Field(default=7, gt=0)  # P-68
    training_export_max_range_days: int = Field(default=366, gt=0)  # P-69


class JobSettings(BaseSettings):
    model_config = _ENV_CONFIG

    job_result_ttl_seconds: int = Field(default=24 * 3600, gt=0)  # P-05
    idempotency_ttl_seconds: int = Field(default=24 * 3600, gt=0)  # P-25
    # A key stays locked this long if a worker dies before storing the response.
    idempotency_lock_seconds: int = Field(default=120, gt=0)
    # Clients reconnect with Last-Event-ID after this, so no stream is held forever.
    sse_max_stream_seconds: int = Field(default=300, gt=0)  # P-53
    stream_ticket_seconds: int = Field(default=60, gt=0)  # P-54 (D-06)


class CacheSettings(BaseSettings):
    model_config = _ENV_CONFIG

    recommendation_cache_seconds: int = Field(default=300, ge=0)  # P-26
    cache_time_bucket_minutes: int = Field(default=15, gt=0)  # P-27
    stale_weather_minutes: int = Field(default=60, gt=0)  # P-28
    stale_disaster_minutes: int = Field(default=15, gt=0)  # P-28
    stale_transport_minutes: int = Field(default=10, gt=0)  # P-28


class TripSettings(BaseSettings):
    model_config = _ENV_CONFIG

    max_trip_days_ahead: int = Field(default=90, gt=0)  # P-55
    trip_alert_scan_minutes: int = Field(default=15, gt=0)  # P-56
    trip_alert_window_hours: int = Field(default=24, gt=0)  # P-57
    trip_alert_reassess_minutes: int = Field(default=60, gt=0)  # P-58
    trip_alert_batch_size: int = Field(default=100, gt=0)  # P-59


class MaintenanceSettings(BaseSettings):
    model_config = _ENV_CONFIG

    reaper_interval_minutes: int = Field(default=5, gt=0)  # P-60
    account_deletion_retry_minutes: int = Field(default=10, gt=0)  # P-61


class RetentionSettings(BaseSettings):
    model_config = _ENV_CONFIG

    retention_recommendation_days: int = Field(default=30, gt=0)  # P-21
    retention_conversation_days: int = Field(default=30, gt=0)  # P-22
    retention_feedback_days: int = Field(default=180, gt=0)  # P-23
    retention_audit_days: int = Field(default=365, gt=0)  # P-24
    retention_prediction_days: int = Field(default=365, gt=0)  # P-46
    retention_trip_days_after_departure: int = Field(default=30, gt=0)  # P-47
    data_export_ttl_days: int = Field(default=7, gt=0)  # P-49
    purge_cron: str = "0 3 * * *"  # P-50
    purge_timezone: str = "Asia/Bangkok"  # P-50
    data_export_url_seconds: int = Field(default=900, gt=0)  # P-62
    data_export_cooldown_hours: int = Field(default=24, gt=0)  # P-63

    @field_validator("purge_cron")
    @classmethod
    def _five_fields(cls, value: str) -> str:
        if len(value.split()) != 5:
            raise ValueError("use a five-field cron expression such as '0 3 * * *'")
        return value

    @field_validator("purge_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        from zoneinfo import available_timezones

        if value not in available_timezones():
            raise ValueError("use an IANA timezone name")
        return value


class ObjectStorageSettings(BaseSettings):
    """S3-compatible storage for data exports (MinIO in development, D-84)."""

    model_config = _ENV_CONFIG

    # host:port the services use; empty disables data export (503).
    object_storage_endpoint: str | None = None
    # Base URL the user's browser uses for download links, e.g. http://localhost:9000.
    object_storage_public_url: str | None = None
    object_storage_access_key: str | None = None
    object_storage_secret_key: SecretStr | None = None
    object_storage_bucket: str = "tsa-exports"
    object_storage_secure: bool = False
    object_storage_region: str = "us-east-1"

    @field_validator(
        "object_storage_endpoint",
        "object_storage_public_url",
        "object_storage_access_key",
        "object_storage_secret_key",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        return value or None

    @property
    def enabled(self) -> bool:
        return bool(
            self.object_storage_endpoint
            and self.object_storage_access_key
            and self.object_storage_secret_key
        )


class PrivacySettings(BaseSettings):
    model_config = _ENV_CONFIG

    log_geohash_precision: int = Field(default=5, ge=1, le=12)  # P-20
    prediction_geohash_precision: int = Field(default=5, ge=1, le=12)  # P-48


class ObservabilitySettings(BaseSettings):
    model_config = _ENV_CONFIG

    log_level: str = "INFO"
    log_json: bool = True
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "travel-safety-api"
    # /ready and /metrics answer only callers from these networks (D-90).
    ops_allowed_networks: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(_PRIVATE_NETWORKS)
    )
    ready_timeout_seconds: float = Field(default=2.0, gt=0)
    ready_agent_cache_seconds: int = Field(default=10, gt=0)  # P-66
    service_status_cache_seconds: int = Field(default=30, gt=0)  # P-65
    service_status_window_minutes: int = Field(default=15, gt=0)  # P-64
    # Port of the worker's own /metrics server; 0 turns it off (D-91).
    worker_metrics_port: int = Field(default=0, ge=0, le=65535)

    @field_validator("ops_allowed_networks", mode="before")
    @classmethod
    def _split_networks(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("ops_allowed_networks")
    @classmethod
    def _valid_networks(cls, value: list[str]) -> list[str]:
        for item in value:
            ip_network(item, strict=False)  # raises ValueError for a bad entry
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"unsupported log level: {value}")
        return level

    @field_validator("otel_exporter_otlp_endpoint", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        return value or None


class SafetySettings(BaseSettings):
    model_config = _ENV_CONFIG

    low_confidence_threshold: float = Field(default=0.5, ge=0, le=1)  # P-51


class SecretSettings(BaseSettings):
    model_config = _ENV_CONFIG

    pseudonym_secret: SecretStr | None = None
    ip_hash_secret: SecretStr | None = None
    # key-id:base64(32 bytes) pairs, active key first (D-81).
    column_encryption_keys: SecretStr | None = None

    @field_validator("pseudonym_secret", "ip_hash_secret", "column_encryption_keys", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        return value or None

    @field_validator("column_encryption_keys")
    @classmethod
    def _valid_keys(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            from app.core.encryption import parse_keys

            parse_keys(value.get_secret_value())
        return value


class Settings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    limits: LimitSettings = Field(default_factory=LimitSettings)
    admin: AdminSettings = Field(default_factory=AdminSettings)
    jobs: JobSettings = Field(default_factory=JobSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    trips: TripSettings = Field(default_factory=TripSettings)
    maintenance: MaintenanceSettings = Field(default_factory=MaintenanceSettings)
    retention: RetentionSettings = Field(default_factory=RetentionSettings)
    storage: ObjectStorageSettings = Field(default_factory=ObjectStorageSettings)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    secrets: SecretSettings = Field(default_factory=SecretSettings)

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.app.is_production and self.auth.dev_jwt_signing_key is not None:
            raise ValueError("DEV_JWT_SIGNING_KEY must not be set outside dev/test")
        if self.app.is_production:
            missing = [
                name.upper()
                for name in ("pseudonym_secret", "ip_hash_secret", "column_encryption_keys")
                if getattr(self.secrets, name) is None
            ]
            if missing:
                raise ValueError(f"required outside dev/test: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
