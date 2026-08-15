import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.database import get_session
from api.core.security import (
    create_token,
    decode_token,
    get_current_user,
    hash_password,
    resolve_user_from_token,
    set_auth_cookies,
    verify_password,
)
from api.models import User, UserProfile
from api.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from api.services.profile_security import set_profile_owner

router = APIRouter(prefix="/api/auth", tags=["auth"])
Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _supabase_headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.supabase_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Auth is not configured")
    return {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
        "Content-Type": "application/json",
    }


async def _supabase_request(path: str, payload: dict[str, str]) -> dict[str, object]:
    settings = get_settings()
    if not settings.supabase_url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Supabase Auth is not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/{path}",
                headers=_supabase_headers(),
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication provider unavailable"
        ) from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.is_error:
        message = (
            body.get("msg") or body.get("error_description") or body.get("message")
            if isinstance(body, dict)
            else None
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED if response.status_code in {400, 401} else 502,
            str(message or "Authentication request failed"),
        )
    if not isinstance(body, dict):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Authentication response is invalid")
    return body


def _external_user(body: dict[str, object]) -> UserResponse | None:
    raw_user = body.get("user")
    if not isinstance(raw_user, dict):
        return None
    raw_created = raw_user.get("created_at")
    try:
        created_at = (
            datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
            if raw_created
            else datetime.now(UTC)
        )
        return UserResponse(
            id=uuid.UUID(str(raw_user["id"])),
            email=str(raw_user["email"]),
            is_active=True,
            created_at=created_at,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Authentication user is invalid") from exc


def _external_response(body: dict[str, object], response: Response) -> AuthResponse:
    access = body.get("access_token")
    refresh = body.get("refresh_token")
    if isinstance(access, str) and isinstance(refresh, str):
        set_auth_cookies(response, access, refresh)
    user = _external_user(body)
    pending = not isinstance(access, str)
    return AuthResponse(
        user=user,
        access_token=access if isinstance(access, str) else None,
        verification_required=pending,
        message="Check your email to verify your account" if pending else None,
    )


def _tokens(user: User) -> tuple[str, str]:
    return (
        create_token(user.id, "access", timedelta(minutes=30)),
        create_token(user.id, "refresh", timedelta(days=7)),
    )


@router.get("/oauth/{provider}", response_class=RedirectResponse)
async def oauth_login(
    provider: Literal["google", "github", "linkedin_oidc"],
    redirect_to: Annotated[str | None, Query(max_length=1000)] = None,
) -> RedirectResponse:
    settings = get_settings()
    if not settings.supabase_auth_enabled or not settings.supabase_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "OAuth is not enabled")
    allowed_origins = [origin.rstrip("/") for origin in settings.cors_origins]
    if not allowed_origins:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "OAuth redirect is not configured")
    destination = redirect_to or f"{allowed_origins[0]}/auth/callback"
    if not any(
        destination == origin or destination.startswith(f"{origin}/") for origin in allowed_origins
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth redirect is not allowed")
    query = urlencode({"provider": provider, "redirect_to": destination})
    return RedirectResponse(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/authorize?{query}",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response, session: Session) -> AuthResponse:
    if get_settings().supabase_auth_enabled:
        body = await _supabase_request(
            "signup", {"email": payload.email.lower(), "password": payload.password}
        )
        return _external_response(body, response)
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    session.add(user)
    try:
        await session.flush()
        await set_profile_owner(session, user.id)
        session.add(UserProfile(user_id=user.id))
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered") from exc
    await session.refresh(user)
    access, refresh = _tokens(user)
    set_auth_cookies(response, access, refresh)
    return AuthResponse(user=UserResponse.model_validate(user), access_token=access)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, response: Response, session: Session) -> AuthResponse:
    if get_settings().supabase_auth_enabled:
        body = await _supabase_request(
            "token?grant_type=password",
            {"email": payload.email.lower(), "password": payload.password},
        )
        return _external_response(body, response)
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if (
        not user
        or user.password_hash.startswith("!")
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is inactive")
    access, refresh = _tokens(user)
    set_auth_cookies(response, access, refresh)
    return AuthResponse(user=UserResponse.model_validate(user), access_token=access)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    response: Response,
    session: Session,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> AuthResponse:
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is missing")
    if get_settings().supabase_auth_enabled and (
        get_settings().auth_mode == "supabase" or refresh_token.count(".") != 2
    ):
        body = await _supabase_request(
            "token?grant_type=refresh_token", {"refresh_token": refresh_token}
        )
        return _external_response(body, response)
    user_id = decode_token(refresh_token, "refresh")
    user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is no longer active")
    access, new_refresh = _tokens(user)
    set_auth_cookies(response, access, new_refresh)
    return AuthResponse(user=UserResponse.model_validate(user), access_token=access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    access_token: Annotated[str | None, Cookie(alias="access_token")] = None,
) -> None:
    if get_settings().supabase_auth_enabled and access_token and get_settings().supabase_url:
        supabase_url = get_settings().supabase_url
        assert supabase_url is not None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{supabase_url.rstrip('/')}/auth/v1/logout",
                    headers={**_supabase_headers(), "Authorization": f"Bearer {access_token}"},
                )
        except (httpx.HTTPError, HTTPException):
            pass
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth")


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/session", response_model=UserResponse | None)
async def session_user(
    session: Session,
    access_token: Annotated[str | None, Cookie(alias="access_token")] = None,
) -> UserResponse | None:
    if not access_token:
        return None
    try:
        user = await resolve_user_from_token(access_token, session)
    except HTTPException:
        return None
    return UserResponse.model_validate(user)
