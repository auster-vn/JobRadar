from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = "JobRadar VN"
    app_env: Literal["development", "test", "production"] = "development"
    source_revision: str = Field(default="local", min_length=1, max_length=128)
    log_level: str = "INFO"
    log_json: bool = False
    database_url: str = "postgresql+asyncpg://jobradarvn:jobradarvn@localhost:5432/jobradarvn"
    migration_database_url: str | None = None
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=5, ge=0, le=20)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=60)
    database_pool_recycle_seconds: int = Field(default=300, ge=30, le=3600)
    database_statement_cache_size: int = Field(default=0, ge=0, le=1024)
    redis_url: str = "redis://localhost:6379/0"
    upstash_redis_rest_url: str | None = None
    upstash_redis_rest_token: str | None = None
    cache_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    jwt_secret_key: str = Field(  # noqa: S105
        default="development-only-secret-change-me",
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET"),
    )
    admin_api_key: str = "development-admin-key"
    cv_encryption_key: str = "development-cv-encryption-key-change-me"  # noqa: S105
    cron_secret: str = "development-cron-secret-change-me"  # noqa: S105
    metrics_token: str | None = None
    auth_mode: Literal["local", "supabase", "hybrid"] = "local"
    supabase_url: str | None = None
    supabase_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_KEY", "SUPABASE_ANON_KEY"),
    )
    supabase_jwt_secret: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "candidate-files"
    supabase_jwt_audience: str = "authenticated"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    max_jobs_per_page: int = Field(default=50, ge=1, le=100)
    max_alerts_per_user: int = Field(default=10, ge=1, le=50)
    max_alert_deliveries_per_run: int = Field(default=25, ge=1, le=100)
    daily_recommendation_user_limit: int = Field(default=50, ge=1, le=500)
    daily_recommendation_job_limit: int = Field(default=50, ge=1, le=200)
    daily_recommendations_per_user: int = Field(default=5, ge=1, le=20)
    daily_recommendation_min_score: int = Field(default=65, ge=0, le=100)
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
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ai_provider: Literal[
        "deterministic", "openai", "deepseek", "openrouter", "gemini", "ollama"
    ] = "deterministic"
    ai_model: str = "jobradar-deterministic-v1"
    ai_fallback_providers: Annotated[list[str], NoDecode] = Field(default_factory=list)
    ai_token_budget: int = Field(default=1200, ge=128, le=16000)
    ai_request_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
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

    @field_validator("ai_fallback_providers", mode="before")
    @classmethod
    def parse_provider_list(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value

    @property
    def effective_migration_database_url(self) -> str:
        return self.migration_database_url or self.database_url

    @property
    def supabase_auth_enabled(self) -> bool:
        return self.auth_mode in {"supabase", "hybrid"} and bool(self.supabase_url)

    def ai_api_key(self, provider: str) -> str | None:
        return {
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "openrouter": self.openrouter_api_key,
            "gemini": self.gemini_api_key,
            "ollama": "local",
            "deterministic": "local",
        }.get(provider)

    def validate_production_secrets(self) -> None:
        if self.app_env != "production":
            return
        insecure = {
            "development-only-secret-change-me",
            "development-admin-key",
            "development-cv-encryption-key-change-me",
            "development-cron-secret-change-me",
            "replace-with-at-least-32-random-characters",
            "replace-with-a-separate-cv-encryption-key",
            "replace-with-a-separate-admin-key",
            "replace-with-a-separate-cron-secret",
        }
        if self.jwt_secret_key in insecure or len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must be a random value of at least 32 characters")
        if self.admin_api_key in insecure or len(self.admin_api_key) < 24:
            raise ValueError("ADMIN_API_KEY must be a random value of at least 24 characters")
        if self.cv_encryption_key in insecure or len(self.cv_encryption_key) < 32:
            raise ValueError("CV_ENCRYPTION_KEY must be a random value of at least 32 characters")
        if self.cron_secret in insecure or len(self.cron_secret) < 32:
            raise ValueError("CRON_SECRET must be a random value of at least 32 characters")
        secrets = {
            self.jwt_secret_key,
            self.admin_api_key,
            self.cv_encryption_key,
            self.cron_secret,
        }
        if len(secrets) != 4:
            raise ValueError("Production secrets must be distinct")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS cannot contain '*' in production")
        if self.auth_mode == "supabase" and (not self.supabase_url or not self.supabase_key):
            raise ValueError("Supabase auth requires SUPABASE_URL and SUPABASE_KEY")
        for provider in [self.ai_provider, *self.ai_fallback_providers]:
            if provider not in {
                "deterministic",
                "openai",
                "deepseek",
                "openrouter",
                "gemini",
                "ollama",
            }:
                raise ValueError(f"Unsupported AI provider: {provider}")
            if provider not in {"deterministic", "ollama"} and not self.ai_api_key(provider):
                raise ValueError(f"{provider.upper()} API key is required when provider is enabled")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production_secrets()
    return settings
