import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Literal

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from jwt.types import Options
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.database import get_session
from api.models import User, UserProfile

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' https: data:",
}
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def create_token(
    user_id: uuid.UUID,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": token_type,
            "iat": now,
            "exp": now + expires_delta,
        },
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )


def _local_claims(token: str, expected_type: Literal["access", "refresh"]) -> dict[str, object]:
    payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise InvalidTokenError("incorrect token type")
    return payload


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=5)


def _supabase_claims(token: str) -> dict[str, object]:
    settings = get_settings()
    if not settings.supabase_url:
        raise InvalidTokenError("Supabase URL is not configured")
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    options: Options = {"require": ["exp", "iat", "sub"]}
    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            issuer=issuer,
            options=options,
        )
    jwks_url = f"{issuer}/.well-known/jwks.json"
    signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience=settings.supabase_jwt_audience,
        issuer=issuer,
        options=options,
    )


def decode_claims(
    token: str, expected_type: Literal["access", "refresh"] = "access"
) -> dict[str, object]:
    settings = get_settings()
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        has_external_issuer = isinstance(unverified.get("iss"), str)
        use_supabase = (
            expected_type == "access"
            and settings.supabase_auth_enabled
            and (settings.auth_mode == "supabase" or has_external_issuer)
        )
        if use_supabase:
            return _supabase_claims(token)
        if settings.auth_mode == "supabase":
            raise InvalidTokenError("Only Supabase access tokens are accepted")
        return _local_claims(token, expected_type)
    except (InvalidTokenError, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> uuid.UUID:
    try:
        payload = decode_claims(token, expected_type)
        return uuid.UUID(str(payload["sub"]))
    except (InvalidTokenError, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    secure = get_settings().app_env == "production"
    response.set_cookie(
        "access_token",
        access,
        max_age=30 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/auth",
    )


async def resolve_user_from_token(token: str, session: AsyncSession) -> User:
    claims = await asyncio.to_thread(decode_claims, token, "access")
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject") from exc
    user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user and get_settings().supabase_auth_enabled:
        email = claims.get("email")
        if not isinstance(email, str) or not email:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authenticated email is required")
        user = User(
            id=user_id,
            email=email.lower(),
            password_hash="!supabase-managed",  # noqa: S106
            is_active=True,
        )
        session.add(user)
        session.add(UserProfile(user_id=user_id))
        try:
            await session.commit()
            await session.refresh(user)
        except Exception:
            await session.rollback()
            user = await session.scalar(
                select(User).where(User.id == user_id, User.is_active.is_(True))
            )
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is no longer active")
    return user


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    access_cookie: Annotated[str | None, Cookie(alias="access_token")] = None,
) -> User:
    token = credentials.credentials if credentials else access_cookie
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return await resolve_user_from_token(token, session)


async def security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    return response


async def csrf_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    settings = get_settings()
    unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    uses_cookie_auth = bool(request.cookies.get("access_token")) and not request.headers.get(
        "Authorization"
    )
    if settings.app_env == "production" and unsafe and uses_cookie_auth:
        origin = request.headers.get("Origin", "").rstrip("/")
        allowed = {item.rstrip("/") for item in settings.cors_origins}
        if origin not in allowed:
            return Response(
                content='{"detail":"Origin validation failed"}',
                status_code=status.HTTP_403_FORBIDDEN,
                media_type="application/json",
            )
    return await call_next(request)
