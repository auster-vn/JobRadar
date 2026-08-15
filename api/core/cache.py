import json
from typing import Any

import httpx
from redis.asyncio import Redis

from api.core.config import get_settings


class CacheUnavailable(RuntimeError):
    """Raised when neither the Upstash REST API nor Redis is reachable."""


class Cache:
    def __init__(self) -> None:
        settings = get_settings()
        self._rest_url = (
            settings.upstash_redis_rest_url.rstrip("/") if settings.upstash_redis_rest_url else None
        )
        self._rest_token = settings.upstash_redis_rest_token
        self._redis: Redis | None = None
        if not self._rest_url:
            self._redis = Redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            )

    async def _rest(self, command: list[str | int]) -> Any:
        if not self._rest_url or not self._rest_token:
            raise CacheUnavailable("Upstash REST credentials are incomplete")
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.post(
                    self._rest_url,
                    headers={"Authorization": f"Bearer {self._rest_token}"},
                    json=command,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CacheUnavailable("Upstash REST request failed") from exc
        if not isinstance(payload, dict) or "result" not in payload:
            raise CacheUnavailable("Upstash REST returned an invalid response")
        return payload["result"]

    async def get_text(self, key: str) -> str | None:
        try:
            if self._rest_url:
                value = await self._rest(["GET", key])
            else:
                assert self._redis is not None
                value = await self._redis.get(key)
        except Exception as exc:
            if isinstance(exc, CacheUnavailable):
                raise
            raise CacheUnavailable("Redis GET failed") from exc
        return str(value) if value is not None else None

    async def set_text(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            if self._rest_url:
                await self._rest(["SET", key, value, "EX", ttl_seconds])
            else:
                assert self._redis is not None
                await self._redis.set(key, value, ex=ttl_seconds)
        except Exception as exc:
            if isinstance(exc, CacheUnavailable):
                raise
            raise CacheUnavailable("Redis SET failed") from exc

    async def get_json(self, key: str) -> Any | None:
        raw = await self.get_text(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            await self.delete(key)
            return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self.set_text(
            key,
            json.dumps(value, separators=(",", ":"), default=str),
            ttl_seconds,
        )

    async def delete(self, key: str) -> None:
        try:
            if self._rest_url:
                await self._rest(["DEL", key])
            else:
                assert self._redis is not None
                await self._redis.delete(key)
        except Exception as exc:
            if isinstance(exc, CacheUnavailable):
                raise
            raise CacheUnavailable("Redis DEL failed") from exc

    async def increment(self, key: str, ttl_seconds: int) -> int:
        try:
            if self._rest_url:
                result = await self._rest(["INCR", key])
                if int(result) == 1:
                    await self._rest(["EXPIRE", key, ttl_seconds])
            else:
                assert self._redis is not None
                result = await self._redis.incr(key)
                if int(result) == 1:
                    await self._redis.expire(key, ttl_seconds)
        except Exception as exc:
            if isinstance(exc, CacheUnavailable):
                raise
            raise CacheUnavailable("Redis increment failed") from exc
        return int(result)

    async def ping(self) -> bool:
        try:
            if self._rest_url:
                return str(await self._rest(["PING"])).upper() == "PONG"
            assert self._redis is not None
            return bool(await self._redis.ping())
        except CacheUnavailable:
            return False
        except Exception:
            return False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()


cache = Cache()
