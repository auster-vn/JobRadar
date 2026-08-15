import re
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx

from api.core.config import get_settings


class StorageUnavailable(RuntimeError):
    pass


def storage_enabled() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _headers(content_type: str | None = None) -> dict[str, str]:
    settings = get_settings()
    key = settings.supabase_service_role_key
    if not key:
        raise StorageUnavailable("SUPABASE_SERVICE_ROLE_KEY is not configured")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    if content_type:
        headers["Content-Type"] = content_type
        headers["x-upsert"] = "true"
    return headers


def _object_path(user_id: uuid.UUID, filename: str | None) -> str:
    suffix = Path(filename or "resume.txt").suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = ".bin"
    return f"{user_id}/cv/{uuid.uuid4().hex}{suffix}"


async def upload_cv(
    user_id: uuid.UUID,
    filename: str | None,
    content: bytes,
    content_type: str | None,
) -> str | None:
    if not storage_enabled():
        return None
    settings = get_settings()
    assert settings.supabase_url is not None
    path = _object_path(user_id, filename)
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{quote(settings.supabase_storage_bucket, safe='')}/{quote(path, safe='/')}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                headers=_headers(content_type or "application/octet-stream"),
                content=content,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise StorageUnavailable("CV upload to Supabase Storage failed") from exc
    return path


async def delete_cv(path: str | None) -> None:
    if not path or not storage_enabled():
        return
    settings = get_settings()
    assert settings.supabase_url is not None
    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{quote(settings.supabase_storage_bucket, safe='')}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                "DELETE",
                url,
                headers={**_headers(), "Content-Type": "application/json"},
                json={"prefixes": [path]},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise StorageUnavailable("CV deletion from Supabase Storage failed") from exc
