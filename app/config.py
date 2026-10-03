import os
from typing import Mapping

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    app_name: str = "ResolveOS"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT", "environment"))
    database_url: str = Field(default="", validation_alias=AliasChoices("DATABASE_URL", "database_url"))
    database_echo: bool = False
    api_prefix: str = "/api"
    api_version: str = "v1"
    log_level: str = "INFO"
    confirmation_window_seconds: int = Field(default=300, ge=0)
    workflow_deadline_seconds: int = Field(default=1800, ge=0)
    api_timeout_ms: int = Field(default=30000, ge=1)
    correlation_event_window_seconds: int = Field(default=1800, ge=0)
    correlation_batch_size: int = Field(default=200, ge=1, le=500)
    correlation_candidate_limit: int = Field(default=1000, ge=1)
    correlation_event_limit: int = Field(default=10000, ge=1)
    correlation_pair_limit: int = Field(default=5000, ge=1)
    orchestration_lease_seconds: int = Field(default=60, ge=1, le=3600)
    orchestration_max_attempts: int = Field(default=3, ge=1, le=10)
    orchestration_backoff_seconds: int = Field(default=5, ge=1, le=3600)
    orchestration_backoff_cap_seconds: int = Field(default=300, ge=1, le=86400)
    orchestration_fairness_seconds: int = Field(default=300, ge=1, le=86400)
    orchestration_poll_limit: int = Field(default=100, ge=1, le=500)
    orchestration_sla_interval_seconds: int = Field(default=60, ge=1, le=3600)
    orchestration_dev_auth_enabled: bool = False
    orchestration_dev_worker_token: SecretStr | None = None
    orchestration_dev_reviewer_token: SecretStr | None = None
    orchestration_dev_reviewer_id: str = "development-reviewer"
    investigator_live_enabled: bool = False
    openai_api_key: SecretStr | None = None
    investigator_model: str = ""
    investigator_model_version: str = ""
    investigator_timeout_seconds: float = Field(default=20, gt=0, le=120)
    investigator_max_iterations: int = Field(default=4, ge=1, le=10)
    investigator_max_tool_calls: int = Field(default=12, ge=1, le=30)
    investigator_token_budget: int = Field(default=16000, ge=100, le=100000)
    investigator_cost_budget: float = Field(default=0.10, gt=0)
    investigator_input_cost_per_million: float = Field(default=0, ge=0)
    investigator_output_cost_per_million: float = Field(default=0, ge=0)
    supervisor_max_review_cycles: int = Field(default=2, ge=1, le=5)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        if not source.get("DATABASE_URL", "").strip():
            raise ValueError("DATABASE_URL is required")
        normalized: dict[str, str] = {}
        for key, value in source.items():
            if value is None:
                continue
            normalized_key = key.lower()
            if normalized_key == "app_env":
                normalized["environment"] = value
            elif normalized_key == "database_url":
                normalized["database_url"] = value
            else:
                normalized[normalized_key] = value
        return cls(**normalized)


def get_settings() -> Settings:
    # Invalid production configuration must never silently become development auth.
    return Settings()
