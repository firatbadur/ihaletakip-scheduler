"""Application configuration loaded from environment variables."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Firebase
    firebase_project_id: str = Field(default="ihale-53fbf")
    firebase_credentials_path: str = Field(
        default="/secrets/serviceAccountKey.json",
        description="Path to Firebase service account JSON",
    )

    # EKAP
    ekap_base_url: str = Field(default="https://ekapv2.kik.gov.tr")
    ekap_signing_key: str = Field(default="Qm2LtXR0aByP69vZNKef4wMJ")
    ekap_rate_per_min: int = Field(default=30, ge=1)
    ekap_concurrency: int = Field(default=3, ge=1)

    # Scheduler crons (Europe/Istanbul)
    alarm_cron: str = Field(default="0 9 * * *")
    saved_filter_cron: str = Field(default="0 10 * * *")
    interest_cron: str = Field(default="0 8-17 * * *")

    # InterestJob limits
    interest_daily_cap: int = Field(default=3, ge=1)
    interest_dedup_days: int = Field(default=7, ge=1)

    # Redis
    redis_url: str = Field(default="redis://redis:6379/0")

    # Runtime
    timezone: str = Field(default="Europe/Istanbul")
    log_level: str = Field(default="INFO")
    log_dir: str = Field(default="/data/logs")

    # Feature flags
    dry_run: bool = Field(default=False)
    only_beta_users: bool = Field(default=False)

    # HTTP
    http_timeout_seconds: float = Field(default=30.0)
    jitter_min_ms: int = Field(default=200)
    jitter_max_ms: int = Field(default=800)


settings = Settings()
