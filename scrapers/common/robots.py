import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from scrapers.common.rate_limiter import DomainRateLimiter


@dataclass(slots=True)
class CachedPolicy:
    parser: RobotFileParser
    expires_at: float


class RobotsPolicy:
    def __init__(
        self,
        client: httpx.AsyncClient,
        user_agent: str,
        ttl_seconds: int = 86400,
        limiter: DomainRateLimiter | None = None,
    ) -> None:
        self.client = client
        self.user_agent = user_agent
        self.ttl_seconds = ttl_seconds
        self.limiter = limiter
        self._cache: dict[str, CachedPolicy] = {}

    async def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cached = self._cache.get(origin)
        if cached and cached.expires_at > time.monotonic():
            return cached.parser.can_fetch(self.user_agent, url)

        robots_url = f"{origin}/robots.txt"
        parser = RobotFileParser(robots_url)
        try:
            if self.limiter:
                await self.limiter.wait(parsed.netloc)
            response = await self.client.get(robots_url)
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        parser.parse(response.text.splitlines())
        self._cache[origin] = CachedPolicy(parser, time.monotonic() + self.ttl_seconds)
        return parser.can_fetch(self.user_agent, url)
