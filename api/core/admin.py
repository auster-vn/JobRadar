import asyncio
import hmac
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from api.core.config import get_settings
from api.core.security import bearer, decode_claims


async def require_admin_key(
    key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
    access_cookie: Annotated[str | None, Cookie(alias="access_token")] = None,
) -> None:
    expected = get_settings().admin_api_key
    if key is not None and hmac.compare_digest(key, expected):
        return
    token = credentials.credentials if credentials else access_cookie
    if token and get_settings().supabase_auth_enabled:
        try:
            claims = await asyncio.to_thread(decode_claims, token, "access")
        except HTTPException:
            claims = {}
        app_metadata = claims.get("app_metadata")
        metadata_role = app_metadata.get("role") if isinstance(app_metadata, dict) else None
        if claims.get("role") == "service_role" or metadata_role == "admin":
            return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Administrator authentication required")
