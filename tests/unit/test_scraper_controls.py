import httpx
import pytest

from scrapers.common.browser import PlaywrightPageRenderer, browser_compatible_user_agent
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


def test_browser_user_agent_retains_declared_bot_identity() -> None:
    declared = "JobRadar-Test-Bot/1.0 (+https://example.com/bot)"

    rendered = browser_compatible_user_agent(declared)

    assert rendered.startswith("Mozilla/5.0")
    assert rendered.endswith(declared)


@pytest.mark.asyncio
async def test_browser_renderer_rejects_non_allowlisted_url_before_launch() -> None:
    renderer = PlaywrightPageRenderer(
        "JobRadar-Test-Bot/1.0",
        "bot@example.com",
        allowed_hosts={"jobs.example.com"},
    )

    with pytest.raises(ValueError, match="outside the HTTPS source allowlist"):
        await renderer.render(
            "https://untrusted.example/private",
            wait_for_selector=".job-card",
        )


@pytest.mark.asyncio
async def test_browser_renderer_isolates_each_render_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePage:
        url = "https://jobs.example.com/listing"

        async def goto(self, *_: object, **__: object) -> None:
            return None

        async def wait_for_selector(self, *_: object, **__: object) -> None:
            return None

        async def content(self) -> str:
            return "<html>jobs</html>"

    class FakeContext:
        def __init__(self) -> None:
            self.closed = False

        async def new_page(self) -> FakePage:
            return FakePage()

        async def close(self) -> None:
            self.closed = True

    class FakeBrowser:
        def __init__(self) -> None:
            self.contexts: list[FakeContext] = []

        async def new_context(self, **_: object) -> FakeContext:
            context = FakeContext()
            self.contexts.append(context)
            return context

    renderer = PlaywrightPageRenderer(
        "JobRadar-Test-Bot/1.0",
        "bot@example.com",
        allowed_hosts={"jobs.example.com"},
    )
    browser = FakeBrowser()

    async def get_browser() -> FakeBrowser:
        return browser

    monkeypatch.setattr(renderer, "_ensure_browser", get_browser)

    for _ in range(2):
        assert (
            await renderer.render(
                "https://jobs.example.com/listing",
                wait_for_selector=".job-card",
            )
            == "<html>jobs</html>"
        )

    assert len(browser.contexts) == 2
    assert all(context.closed for context in browser.contexts)


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
