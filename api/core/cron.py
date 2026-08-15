import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from api.core.config import get_settings


async def require_cron_secret(
    supplied: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
) -> None:
    expected = get_settings().cron_secret
    if supplied is not None and hmac.compare_digest(supplied, expected):
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cron authentication required")
