from typing import Any

import pytest

from api.core.cache import Cache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.expirations[key] = ex

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


def _cache() -> Cache:
    cache = Cache()
    cache._rest_url = None
    cache._redis = FakeRedis()  # type: ignore[assignment]
    return cache


@pytest.mark.asyncio
async def test_json_cache_round_trip() -> None:
    cache = _cache()
    payload: dict[str, Any] = {"jobs": [1, 2], "ready": True}

    await cache.set_json("jobs:test", payload, 30)

    assert await cache.get_json("jobs:test") == payload


@pytest.mark.asyncio
async def test_increment_sets_window_only_on_first_write() -> None:
    cache = _cache()

    assert await cache.increment("rate:test", 61) == 1
    assert await cache.increment("rate:test", 61) == 2
    assert isinstance(cache._redis, FakeRedis)
    assert cache._redis.expirations["rate:test"] == 61
