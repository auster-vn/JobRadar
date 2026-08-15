from typing import cast

import httpx
import pytest

from scrapers.common.browser import PageRenderer
from scrapers.common.http_client import EthicalHttpClient
from scrapers.topcv.scraper import LISTING_URL, SourceBlockedError, TopCVScraper

CARD = """
<div class="job-item-search-result" data-job-id="{job_id}">
 <h3 class="title"><a href="/viec-lam/backend/{job_id}.html"><span>Backend Developer</span></a></h3>
 <span class="company-name">Example Co</span>
 <div class="box-icon"><label class="address">Hôm nay</label></div>
</div>
<span id="job-listing-paginate-text">1 / 2 trang</span>
"""

ONE_PAGE_CARD = CARD.replace("1 / 2 trang", "1 / 1 trang")


class FakeClient:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def get(self, url: str, *, use_cache: bool = True) -> str:
        self.urls.append(url)
        page = 2 if "page=2" in url else 1
        return CARD.format(job_id=100 + page)


@pytest.mark.asyncio
async def test_topcv_scraper_paginates() -> None:
    client = FakeClient()
    jobs = await TopCVScraper(cast(EthicalHttpClient, client)).scrape(max_pages=2)

    assert client.urls == [LISTING_URL, f"{LISTING_URL}?page=2"]
    assert [job.platform_job_id for job in jobs] == ["101", "102"]


@pytest.mark.asyncio
async def test_topcv_scraper_deduplicates_stable_source_ids() -> None:
    class DuplicateClient:
        async def get(self, url: str, *, use_cache: bool = True) -> str:
            return CARD.format(job_id=101)

    jobs = await TopCVScraper(cast(EthicalHttpClient, DuplicateClient())).scrape(max_pages=2)

    assert [job.platform_job_id for job in jobs] == ["101"]


@pytest.mark.asyncio
async def test_topcv_scraper_stops_at_publisher_page_count() -> None:
    class OnePageClient:
        def __init__(self) -> None:
            self.calls = 0

        async def get(self, url: str, *, use_cache: bool = True) -> str:
            self.calls += 1
            return ONE_PAGE_CARD.format(job_id=101)

    client = OnePageClient()
    jobs = await TopCVScraper(cast(EthicalHttpClient, client)).scrape(max_pages=10)

    assert client.calls == 1
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_topcv_scraper_rejects_empty_or_blocked_listing() -> None:
    class EmptyClient:
        async def get(self, url: str, *, use_cache: bool = True) -> str:
            return "<html><title>Just a moment...</title></html>"

    with pytest.raises(SourceBlockedError, match="did not contain"):
        await TopCVScraper(cast(EthicalHttpClient, EmptyClient())).scrape(max_pages=1)


@pytest.mark.asyncio
async def test_topcv_scraper_maps_http_403_to_source_blocked() -> None:
    class BlockedClient:
        async def get(self, url: str, *, use_cache: bool = True) -> str:
            request = httpx.Request("GET", url)
            response = httpx.Response(403, request=request)
            raise httpx.HTTPStatusError("blocked", request=request, response=response)

    with pytest.raises(SourceBlockedError, match="HTTP 403"):
        await TopCVScraper(cast(EthicalHttpClient, BlockedClient())).scrape(max_pages=1)


@pytest.mark.asyncio
async def test_topcv_scraper_switches_to_renderer_after_http_403() -> None:
    class BlockedClient:
        def __init__(self) -> None:
            self.get_urls: list[str] = []
            self.authorized_urls: list[str] = []

        async def get(self, url: str, *, use_cache: bool = True) -> str:
            self.get_urls.append(url)
            request = httpx.Request("GET", url)
            response = httpx.Response(403, request=request)
            raise httpx.HTTPStatusError("blocked", request=request, response=response)

        async def authorize(self, url: str) -> None:
            self.authorized_urls.append(url)

    class FakeRenderer:
        def __init__(self) -> None:
            self.urls: list[str] = []

        async def render(self, url: str, *, wait_for_selector: str) -> str:
            self.urls.append(url)
            assert wait_for_selector == ".job-item-search-result[data-job-id]"
            page = 2 if "page=2" in url else 1
            return CARD.format(job_id=200 + page)

        async def close(self) -> None:
            raise AssertionError("the scraper must not close an injected renderer")

    client = BlockedClient()
    renderer = FakeRenderer()
    jobs = await TopCVScraper(
        cast(EthicalHttpClient, client),
        cast(PageRenderer, renderer),
    ).scrape(max_pages=2)

    assert client.get_urls == [LISTING_URL]
    assert client.authorized_urls == [LISTING_URL, f"{LISTING_URL}?page=2"]
    assert renderer.urls == [LISTING_URL, f"{LISTING_URL}?page=2"]
    assert [job.platform_job_id for job in jobs] == ["201", "202"]


@pytest.mark.asyncio
async def test_topcv_scraper_switches_to_renderer_after_challenge_markup() -> None:
    class ChallengeClient:
        def __init__(self) -> None:
            self.authorized_urls: list[str] = []

        async def get(self, url: str, *, use_cache: bool = True) -> str:
            return "<html><title>Just a moment...</title></html>"

        async def authorize(self, url: str) -> None:
            self.authorized_urls.append(url)

    class FakeRenderer:
        async def render(self, url: str, *, wait_for_selector: str) -> str:
            return ONE_PAGE_CARD.format(job_id=301)

        async def close(self) -> None:
            return None

    client = ChallengeClient()
    jobs = await TopCVScraper(
        cast(EthicalHttpClient, client),
        cast(PageRenderer, FakeRenderer()),
    ).scrape(max_pages=1)

    assert client.authorized_urls == [LISTING_URL]
    assert [job.platform_job_id for job in jobs] == ["301"]


@pytest.mark.asyncio
async def test_topcv_scraper_enforces_page_cap() -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        await TopCVScraper().scrape(max_pages=11)
