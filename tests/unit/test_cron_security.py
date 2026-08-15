import pytest
from fastapi import HTTPException

from api.core.cron import require_cron_secret


@pytest.mark.asyncio
async def test_cron_secret_is_required() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_cron_secret(None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_cron_secret_accepts_configured_value() -> None:
    await require_cron_secret("development-cron-secret-change-me")
