from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_version: str = "0.1.0"
    # No LLM planner yet: intent and planning are rule-based in this version.
    prompt_version: str = "rules-v1"

    # Bearer token Module 02 must send (its AGENT_SERVICE_TOKEN). Empty disables the check,
    # which is only acceptable for local development.
    agent_service_token: SecretStr = SecretStr("")

    decision_service_url: HttpUrl = HttpUrl("http://localhost:8050")
    # False uses Module 04 (weather, transport, disaster, routing), Module 05
    # integration, and Module 06 for real.
    use_mock_tools: bool = False
    transport_provider: str = "longdo"  # "longdo" | "tomtom"
    longdo_api_key: SecretStr = SecretStr("")
    tomtom_api_key: SecretStr = SecretStr("")
    # Public demo server: no key, but rate limited. Point this at a self-hosted OSRM
    # instance for production traffic.
    osrm_base_url: HttpUrl = HttpUrl("https://router.project-osrm.org")

    # Hard limits on one run (03_process.txt: the agent must not run forever).
    max_agent_steps: int = Field(default=12, ge=1, le=50)
    max_tool_calls: int = Field(default=20, ge=1, le=100)
    # Our own cap only. Module 02 sends X-Deadline (60 s for jobs, P-04) and the run stops
    # at the earliest deadline, so this must not be shorter than 02's budget.
    agent_total_timeout: float = Field(default=60, gt=0, le=300)
    tool_timeout_seconds: float = Field(default=15, gt=0, le=60)
    decision_max_attempts: int = Field(default=2, ge=1, le=5)
