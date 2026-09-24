"""
Central configuration for the Recommendation & Feedback service.

Every field here corresponds to a line under "Required configuration" in
01_env.txt. Values are read from environment variables (or a mounted
.env file) — see .env.example for the full list with comments.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Required configuration (01_env.txt) ---
    recommendation_schema_version: str = "1.0.0"
    feedback_retention_days: int = 180
    alert_refresh_interval_seconds: int = 60
    notification_provider_keys: str = ""  # comma-separated; empty = notifications disabled
    emergency_contact_directory_version: str = "1.0.0"
    feature_flag_live_updates: bool = True
    rollout_percentage: int = 100

    # --- Infrastructure ---
    database_url: str = "postgresql+asyncpg://reco_user:change_me@postgres:5432/reco_db"
    redis_url: str = "redis://redis:6379/0"

    # --- Upstream services ---
    decision_engine_url: str = "http://decision-engine:8050"
    decision_engine_timeout_seconds: float = 10.0

    # --- Service ---
    service_port: int = 8080


settings = Settings()
