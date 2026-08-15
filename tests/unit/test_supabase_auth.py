import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from api.core import security
from api.core.config import Settings
from api.routers import auth


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        auth_mode="supabase",
        supabase_url="https://example.supabase.co",
        supabase_key="anon-key",
        supabase_jwt_secret="s" * 40,
    )


def _token(settings: Settings, *, issuer: str | None = None) -> tuple[str, uuid.UUID]:
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    return (
        jwt.encode(
            {
                "sub": str(user_id),
                "email": "candidate@example.com",
                "aud": settings.supabase_jwt_audience,
                "iss": issuer or f"{settings.supabase_url}/auth/v1",
                "iat": now,
                "exp": now + timedelta(minutes=5),
            },
            settings.supabase_jwt_secret,
            algorithm="HS256",
        ),
        user_id,
    )


def test_supabase_access_token_is_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    token, expected_user = _token(settings)

    assert security.decode_token(token, "access") == expected_user


def test_supabase_token_rejects_wrong_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    token, _ = _token(settings, issuer="https://attacker.example/auth/v1")

    with pytest.raises(HTTPException) as exc_info:
        security.decode_token(token, "access")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_oauth_redirect_is_limited_to_configured_frontend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings().model_copy(update={"cors_origins": ["https://app.example.com"]})
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    response = await auth.oauth_login("google", "https://app.example.com/auth/callback")

    assert response.status_code == 307
    assert str(response.headers["location"]).startswith(
        "https://example.supabase.co/auth/v1/authorize?"
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth.oauth_login("google", "https://attacker.example/callback")
    assert exc_info.value.status_code == 400
