"""Settings read from the environment (the root `.env` in docker compose)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "api"
    version: str = Field(default="0.1.0", validation_alias="GIT_SHA")
    environment: str = "dev"
    log_level: str = "INFO"
    log_json: bool = True
    timezone: str = "Asia/Bangkok"
    error_type_base_url: str = "https://errors.football-assistant.local"

    database_url: str = "postgresql+asyncpg://app:app@postgres:5432/football"
    # Empty = in-process store (single worker / tests only).
    redis_url: str = "redis://redis:6379/0"

    # Required: no default, so a missing key stops start-up instead of signing with a known one.
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 8 * 60
    cookie_name: str = "access_token"
    cookie_secure: bool = False
    cors_allowed_origins: list[str] = ["http://localhost:3000"]

    router_url: str = Field(default="http://router:8000", validation_alias="AI_ROUTER_SERVICE_URL")
    router_timeout_seconds: float = 45.0
    router_max_retries: int = 1
    breaker_failure_threshold: int = 5
    breaker_window_seconds: int = 60
    breaker_reset_seconds: int = 30

    football_data_url: str = "http://football-data:8000"
    football_data_timeout_seconds: float = 10.0
    retrieval_url: str = "http://retrieval:8000"
    retrieval_timeout_seconds: float = 10.0
    football_status_cache_seconds: int = 300

    chat_rate_limit_per_minute: int = 20
    login_rate_limit_per_minute: int = 10
    register_rate_limit_per_minute: int = 30
    max_body_bytes: int = 64 * 1024
    history_limit: int = 10
    feedback_wait_seconds: float = 3.0

    seed_admin_password: str = ""
    seed_demo_password: str = ""

    celery_broker_url: str = ""

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url or "memory://"


@lru_cache
def get_settings() -> Settings:
    return Settings()
