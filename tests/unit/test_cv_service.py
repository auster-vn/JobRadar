import pytest
from fastapi import HTTPException

from api.services.cv_service import extract_cv


@pytest.mark.asyncio
async def test_extract_plain_text_cv() -> None:
    text = await extract_cv(
        "profile.txt",
        b"Senior Backend Developer\nPython FastAPI PostgreSQL Docker\nFour years experience",
    )
    assert "FastAPI" in text


@pytest.mark.asyncio
async def test_rejects_mismatched_magic_bytes() -> None:
    with pytest.raises(HTTPException) as error:
        await extract_cv("profile.pdf", b"this is not a pdf document")
    assert error.value.status_code == 415
