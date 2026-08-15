import asyncio
import time
from collections import defaultdict


class DomainRateLimiter:
    def __init__(self, minimum_interval_seconds: float = 5.0) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum interval cannot be negative")
        self.minimum_interval = minimum_interval_seconds
        self._last_request: dict[str, float] = defaultdict(float)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def wait(self, domain: str) -> None:
        async with self._locks[domain]:
            elapsed = time.monotonic() - self._last_request[domain]
            delay = self.minimum_interval - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request[domain] = time.monotonic()
