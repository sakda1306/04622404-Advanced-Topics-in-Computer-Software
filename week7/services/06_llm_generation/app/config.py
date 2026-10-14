"""ค่าตั้งค่า service — ทุกตัวแปรต้องมีค่าตั้งต้น ไม่บังคับต้องตั้ง env"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # provider order
    llm_primary: str = "groq"
    llm_fallback: str = "gemini"

    # groq
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # gemini
    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    llm_mock: bool = False

    max_output_tokens: int = 1500
    report_max_output_tokens: int = 3500

    temperature_grounded: float = 0.2
    temperature_passthrough: float = 0.2
    temperature_report: float = 0.4

    reasoning_effort: str = "low"

    generate_deadline_s: float = 22.0
    report_deadline_s: float = 55.0

    max_context_tokens: int = 6000
    context_char_limit: int = 2500

    moderation_enabled: bool = True
    numeric_guard: str = "strict"  # strict | warn | off

    pii_masking: bool = False
    llm_moderation: bool = False

    log_level: str = "INFO"

    service_version: str = "0.1.0"
    git_sha: str = ""


settings = Settings()
