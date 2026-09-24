from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    decision_policy_version: str = "prototype-v3"
    emergency_catalog_path: Path | None = None
    prompt_version: str = "v1"
    policy_approved: bool = False
    llm_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("llm_api_key", "gemini_api_key"),
    )
    llm_model_explainer: str = "disabled"
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    temperature: float = Field(default=0, ge=0, le=0)
    max_input_tokens: int = Field(default=8000, ge=256, le=32000)
    max_output_tokens: int = Field(default=1500, ge=64, le=8000)
    llm_timeout: float = Field(default=5.0, gt=0, le=60)
    llm_max_attempts: int = Field(default=2, ge=1, le=3)
    supported_locales: str = "th-TH,en-US"
    escalation_rules: str = (
        "missing,stale,conflicting,incomplete,low_confidence,unverified_warning,"
        "partial,freshness_unknown"
    )
    audit_log_path: Path = Path("data/audit.jsonl")

    @field_validator("decision_policy_version")
    @classmethod
    def bundled_policy_only(cls, value: str) -> str:
        if value != "prototype-v3":
            raise ValueError(
                "This release requires prototype-v3; roll back code and policy together"
            )
        return value

    @field_validator("prompt_version")
    @classmethod
    def bundled_prompt_only(cls, value: str) -> str:
        if value not in {"v1", "rules-v1"}:
            raise ValueError("Only prompt v1 is implemented")
        return value

    @field_validator("policy_approved")
    @classmethod
    def no_self_approval(cls, value: bool) -> bool:
        if value:
            raise ValueError("Bundled policy is provisional; an environment flag cannot approve it")
        return value

    @field_validator("supported_locales")
    @classmethod
    def supported_languages(cls, value: str) -> str:
        locales = {part.strip() for part in value.split(",")}
        if not locales or not locales <= {"th-TH", "en-US"}:
            raise ValueError("Supported locales are th-TH and en-US")
        return value

    @field_validator("escalation_rules")
    @classmethod
    def mandatory_escalations(cls, value: str) -> str:
        required = {
            "missing",
            "stale",
            "conflicting",
            "incomplete",
            "low_confidence",
            "unverified_warning",
            "partial",
            "freshness_unknown",
        }
        if {v.strip() for v in value.split(",")} != required:
            raise ValueError("Changing escalation rules requires a new reviewed policy")
        return value

    @property
    def locales(self) -> set[str]:
        return {part.strip() for part in self.supported_locales.split(",")}
