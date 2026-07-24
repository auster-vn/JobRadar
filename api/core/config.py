from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "JobRadar VN"
    app_env: Literal["development", "test", "production"] = "development"
    source_revision: str = Field(default="local", min_length=1, max_length=128)
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://jobradarvn:jobradarvn@localhost:5432/jobradarvn"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "development-only-secret-change-me"  # noqa: S105
    admin_api_key: str = "development-admin-key"
    cv_encryption_key: str = "development-cv-encryption-key-change-me"  # noqa: S105
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    max_jobs_per_page: int = Field(default=50, ge=1, le=100)
    rate_limit_enabled: bool = True
    trust_proxy_headers: bool = False
    scraper_user_agent: str = "JobRadarVN-Research-Bot/1.0 (+https://jobradarvn.com/bot)"
    scraper_contact_email: str = "bot@jobradarvn.com"
    enable_itviec_scraper: bool = False
    enable_topcv_scraper: bool = False
    enable_vietnamworks_scraper: bool = False
    linkedin_access_token: str | None = None
    telegram_bot_token: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mlflow_tracking_uri: str = "sqlite:///artifacts/mlflow.db"
    mlflow_experiment: str = "jobradar-salary"
    salary_model_url: str | None = None
    salary_model_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    salary_holdout_manifest: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def validate_production_secrets(self) -> None:
        if self.app_env != "production":
            return
        insecure = {
            "development-only-secret-change-me",
            "development-admin-key",
            "development-cv-encryption-key-change-me",
            "replace-with-at-least-32-random-characters",
            "replace-with-a-separate-cv-encryption-key",
        }
        if self.jwt_secret_key in insecure or len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must be a random value of at least 32 characters")
        if self.admin_api_key in insecure or len(self.admin_api_key) < 24:
            raise ValueError("ADMIN_API_KEY must be a random value of at least 24 characters")
        if self.cv_encryption_key in insecure or len(self.cv_encryption_key) < 32:
            raise ValueError("CV_ENCRYPTION_KEY must be a random value of at least 32 characters")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production_secrets()
    return settings
