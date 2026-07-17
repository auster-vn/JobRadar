import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from api.core.config import get_settings


async def require_admin_key(
    key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    expected = get_settings().admin_api_key
    if key is None or not hmac.compare_digest(key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid admin key")
