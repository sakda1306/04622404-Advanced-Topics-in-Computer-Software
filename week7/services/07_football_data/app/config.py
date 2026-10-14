"""Configuration is read from environment variables at startup."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./football_data.db"
    football_data_api_key: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    api_football_league_id: int = 39
    api_football_daily_limit: int = 90
    retrieval_url: str = "http://retrieval:8000"
    generation_url: str = "http://generation:8000"
    engines_url: str = "http://engines:8000"
    report_auto_publish: bool = False
    historical_index_enabled: bool = False
    player_index_enabled: bool = False
    coach_index_enabled: bool = False
    index_retry_seconds: float = Field(default=2, gt=0)
    index_retry_max_seconds: float = Field(default=60, gt=0)
    index_transition_timeout_seconds: float = Field(default=120, gt=0)
    version: str = "0.1.0"


def get_settings() -> Settings:
    return Settings()
