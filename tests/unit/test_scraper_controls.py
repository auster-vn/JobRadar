import httpx
import pytest

from scrapers.common.http_client import EthicalHttpClient, RobotsDeniedError
from scrapers.common.rate_limiter import DomainRateLimiter
from scrapers.common.robots import RobotsPolicy


@pytest.mark.asyncio
async def test_robots_policy_caches_and_enforces_rules() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, text="User-agent: *\nDisallow: /private")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        policy = RobotsPolicy(client, "JobRadar-Test", ttl_seconds=60)
        assert await policy.allowed("https://example.com/jobs")
        assert not await policy.allowed("https://example.com/private/profile")
    assert requests == 1


@pytest.mark.asyncio
async def test_robots_policy_fails_closed_on_http_error() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(503))
    async with httpx.AsyncClient(transport=transport) as client:
        policy = RobotsPolicy(client, "JobRadar-Test")
        assert not await policy.allowed("https://example.com/jobs")


def test_rate_limiter_rejects_negative_interval() -> None:
    with pytest.raises(ValueError, match="negative"):
        DomainRateLimiter(-1)


@pytest.mark.asyncio
async def test_rate_limiter_accepts_zero_interval() -> None:
    limiter = DomainRateLimiter(0)
    await limiter.wait("example.com")
    await limiter.wait("example.com")


@pytest.mark.asyncio
async def test_ethical_client_uses_cache() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="listing")

    client = EthicalHttpClient("JobRadar-Test", minimum_interval_seconds=0)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client._robots.client = client._client
    client._robots.allowed = _allow  # type: ignore[method-assign]
    async with client:
        assert await client.get("https://example.com/jobs") == "listing"
        assert await client.get("https://example.com/jobs") == "listing"
    assert calls == 1


@pytest.mark.asyncio
async def test_ethical_client_blocks_disallowed_url() -> None:
    client = EthicalHttpClient("JobRadar-Test", minimum_interval_seconds=0)
    client._robots.allowed = _deny  # type: ignore[method-assign]
    async with client:
        with pytest.raises(RobotsDeniedError):
            await client.get("https://example.com/private")


@pytest.mark.asyncio
async def test_ethical_client_posts_first_party_json_with_cache() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        return httpx.Response(200, json={"data": [1]})

    client = EthicalHttpClient("JobRadar-Test", minimum_interval_seconds=0)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client._robots.client = client._client
    client._robots.allowed = _allow  # type: ignore[method-assign]
    async with client:
        first = await client.post_json(
            "https://api.example.com/search",
            {"page": 0},
            policy_url="https://www.example.com/jobs",
        )
        second = await client.post_json(
            "https://api.example.com/search",
            {"page": 0},
            policy_url="https://www.example.com/jobs",
        )
    assert first == second == {"data": [1]}
    assert calls == 1


@pytest.mark.asyncio
async def test_ethical_client_rejects_cross_domain_policy_url() -> None:
    client = EthicalHttpClient("JobRadar-Test", minimum_interval_seconds=0)
    async with client:
        with pytest.raises(ValueError, match="share a registered domain"):
            await client.post_json(
                "https://api.example.com/search",
                {"page": 0},
                policy_url="https://unrelated.test/jobs",
            )


async def _allow(_: str) -> bool:
    return True


async def _deny(_: str) -> bool:
    return False
