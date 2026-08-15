import pytest

from api.core.config import Settings


def _production_settings(**overrides: str) -> Settings:
    values = {
        "app_env": "production",
        "jwt_secret_key": "j" * 32,
        "admin_api_key": "a" * 24,
        "cv_encryption_key": "c" * 32,
        "cron_secret": "s" * 32,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_production_accepts_independent_strong_secrets() -> None:
    _production_settings().validate_production_secrets()


def test_default_mlflow_tracking_uses_supported_database_backend() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.mlflow_tracking_uri == "sqlite:///artifacts/mlflow.db"


def test_migrations_can_use_direct_database_connection() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url="postgresql+asyncpg://pooler/app",
        migration_database_url="postgresql+asyncpg://direct/app",
    )

    assert settings.effective_migration_database_url == "postgresql+asyncpg://direct/app"


def test_jwt_secret_accepts_goal_compatible_environment_alias() -> None:
    settings = Settings(_env_file=None, JWT_SECRET="z" * 32)  # type: ignore[call-arg]

    assert settings.jwt_secret_key == "z" * 32


def test_production_rejects_documented_admin_placeholder() -> None:
    with pytest.raises(ValueError, match="ADMIN_API_KEY"):
        _production_settings(
            admin_api_key="replace-with-a-separate-admin-key"
        ).validate_production_secrets()


@pytest.mark.parametrize(
    "key",
    ["short", "development-cv-encryption-key-change-me"],
)
def test_production_rejects_weak_cv_encryption_key(key: str) -> None:
    with pytest.raises(ValueError, match="CV_ENCRYPTION_KEY"):
        _production_settings(cv_encryption_key=key).validate_production_secrets()
