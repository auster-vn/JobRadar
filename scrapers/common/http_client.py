import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from scrapers.common.rate_limiter import DomainRateLimiter
from scrapers.common.robots import RobotsPolicy


class RobotsDeniedError(PermissionError):
    pass


@dataclass(slots=True)
class CachedResponse:
    body: str
    expires_at: float


class EthicalHttpClient:
    def __init__(
        self,
        user_agent: str,
        minimum_interval_seconds: float = 5.0,
        cache_ttl_seconds: int = 86400,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept-Language": "en,vi;q=0.9"},
            follow_redirects=True,
            timeout=httpx.Timeout(30),
        )
        self._limiter = DomainRateLimiter(minimum_interval_seconds)
        self._robots = RobotsPolicy(
            self._client,
            user_agent,
            cache_ttl_seconds,
            limiter=self._limiter,
        )
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, CachedResponse] = {}

    @staticmethod
    def _same_registered_domain(first_url: str, second_url: str) -> bool:
        def registered_domain(url: str) -> str:
            labels = (urlparse(url).hostname or "").rstrip(".").split(".")
            return ".".join(labels[-2:]) if len(labels) >= 2 else ".".join(labels)

        first = registered_domain(first_url)
        return bool(first) and first == registered_domain(second_url)

    async def __aenter__(self) -> "EthicalHttpClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get(self, url: str, *, use_cache: bool = True) -> str:
        cached = self._cache.get(url)
        if use_cache and cached and cached.expires_at > time.monotonic():
            return cached.body
        if not await self._robots.allowed(url):
            raise RobotsDeniedError(f"robots.txt does not permit collection: {url}")
        await self._limiter.wait(urlparse(url).netloc)
        response = await self._client.get(url)
        response.raise_for_status()
        self._cache[url] = CachedResponse(response.text, time.monotonic() + self._cache_ttl)
        return response.text

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def post_json(
        self,
        url: str,
        payload: dict[str, object],
        *,
        policy_url: str,
        use_cache: bool = True,
    ) -> Any:
        """POST to a public first-party endpoint after checking its page policy."""
        if not self._same_registered_domain(url, policy_url):
            raise ValueError("API endpoint and robots policy URL must share a registered domain")
        cache_key = f"POST {url}\n{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
        cached = self._cache.get(cache_key)
        if use_cache and cached and cached.expires_at > time.monotonic():
            return json.loads(cached.body)
        if not await self._robots.allowed(policy_url):
            raise RobotsDeniedError(f"robots.txt does not permit collection: {policy_url}")
        await self._limiter.wait(urlparse(url).netloc)
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        body = response.text
        self._cache[cache_key] = CachedResponse(body, time.monotonic() + self._cache_ttl)
        return json.loads(body)
