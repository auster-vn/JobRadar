import pytest

from api.core.config import Settings


def _production_settings(**overrides: str) -> Settings:
    values = {
        "app_env": "production",
        "jwt_secret_key": "j" * 32,
        "admin_api_key": "a" * 24,
        "cv_encryption_key": "c" * 32,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_production_accepts_independent_strong_secrets() -> None:
    _production_settings().validate_production_secrets()


@pytest.mark.parametrize(
    "key",
    ["short", "development-cv-encryption-key-change-me"],
)
def test_production_rejects_weak_cv_encryption_key(key: str) -> None:
    with pytest.raises(ValueError, match="CV_ENCRYPTION_KEY"):
        _production_settings(cv_encryption_key=key).validate_production_secrets()
