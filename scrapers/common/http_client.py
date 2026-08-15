import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from scrapers.common.rate_limiter import DomainRateLimiter
from scrapers.common.robots import RobotsPolicy


class RobotsDeniedError(PermissionError):
    pass


@dataclass(slots=True)
class CachedResponse:
    body: str
    expires_at: float


class EthicalHttpClient:
    MAX_RESPONSE_BYTES = 5 * 1024 * 1024

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

    async def authorize(self, url: str) -> None:
        """Apply robots policy and the shared domain delay before an external fetch."""
        if not await self._robots.allowed(url):
            raise RobotsDeniedError(f"robots.txt does not permit collection: {url}")
        await self._limiter.wait(urlparse(url).netloc)

    @classmethod
    def _validate_response(cls, requested_url: str, response: httpx.Response) -> None:
        if not cls._same_registered_domain(requested_url, str(response.url)):
            raise ValueError("Scraper redirect left the approved source domain")
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > cls.MAX_RESPONSE_BYTES:
            raise ValueError("Scraper response exceeds the configured size limit")
        if len(response.content) > cls.MAX_RESPONSE_BYTES:
            raise ValueError("Scraper response exceeds the configured size limit")

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after", "")
            try:
                return min(30.0, max(0.5, float(retry_after)))
            except ValueError:
                pass
        return min(10.0, float(2**attempt) + 0.25)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json_payload: dict[str, object] | None = None,
        policy_url: str | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            response: httpx.Response | None = None
            try:
                if policy_url:
                    if not await self._robots.allowed(policy_url):
                        raise RobotsDeniedError(
                            f"robots.txt does not permit collection: {policy_url}"
                        )
                    await self._limiter.wait(urlparse(url).netloc)
                else:
                    await self.authorize(url)
                response = await self._client.request(method, url, json=json_payload)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                self._validate_response(url, response)
                return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if not retryable or attempt == 2:
                    raise
                await asyncio.sleep(self._retry_delay(response, attempt))
        assert last_error is not None
        raise last_error

    async def get(self, url: str, *, use_cache: bool = True) -> str:
        cached = self._cache.get(url)
        if use_cache and cached and cached.expires_at > time.monotonic():
            return cached.body
        response = await self._request("GET", url)
        self._cache[url] = CachedResponse(response.text, time.monotonic() + self._cache_ttl)
        return response.text

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
        response = await self._request("POST", url, json_payload=payload, policy_url=policy_url)
        body = response.text
        self._cache[cache_key] = CachedResponse(body, time.monotonic() + self._cache_ttl)
        return json.loads(body)
