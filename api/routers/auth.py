from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_session
from api.core.security import (
    create_token,
    decode_token,
    get_current_user,
    hash_password,
    set_auth_cookies,
    verify_password,
)
from api.models import User, UserProfile
from api.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from api.services.profile_security import set_profile_owner

router = APIRouter(prefix="/api/auth", tags=["auth"])
Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _tokens(user: User) -> tuple[str, str]:
    return (
        create_token(user.id, "access", timedelta(minutes=30)),
        create_token(user.id, "refresh", timedelta(days=7)),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response, session: Session) -> AuthResponse:
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
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
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
    user_id = decode_token(refresh_token, "refresh")
    user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is no longer active")
    access, new_refresh = _tokens(user)
    set_auth_cookies(response, access, new_refresh)
    return AuthResponse(user=UserResponse.model_validate(user), access_token=access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
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
        user_id = decode_token(access_token, "access")
    except HTTPException:
        return None
    user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    return UserResponse.model_validate(user) if user else None
