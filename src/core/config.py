"""Application configuration and settings."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"
    api_version: str = "v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/eam_platform"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AWS
    aws_region: str = "ap-southeast-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket_name: str = "eam-platform-documents"
    s3_bucket_region: str = "ap-southeast-1"

    # Document Storage
    storage_backend: str = "local"  # "local" or "s3"

    # Auth (OIDC/OAuth2)
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_audience: str = ""

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # CORS
    cors_origins: List[str] = ["*"]

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    audit_log_archive_after_days: int = 30
    audit_log_retention_days: int = 365
    audit_log_archive_batch_size: int = 5000

    task_sla_interval_seconds: int = 900
    task_sla_escalation_cooldown_hours: int = 4
    task_sla_max_escalation_level: int = 2

    platform_roles: List[str] = ["super_admin", "platform_admin", "platform_user"]
    platform_admin_roles: List[str] = ["super_admin", "platform_admin"]
    tenant_admin_roles: List[str] = ["tenant_admin"]
    supervisor_roles: List[str] = ["tenant_admin", "eam_supervisor"]
    all_staff_roles: List[str] = ["tenant_admin", "eam_supervisor", "eam_staff"]

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()

