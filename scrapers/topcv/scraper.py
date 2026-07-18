import httpx

from api.core.config import get_settings
from scrapers.common.browser import PageRenderer, PageRenderError, PlaywrightPageRenderer
from scrapers.common.http_client import EthicalHttpClient
from scrapers.common.validator import RawJobValidator
from scrapers.topcv.parser import listing_page_count, parse_listing

LISTING_URL = "https://www.topcv.vn/tim-viec-lam-software-engineer"
JOB_CARD_SELECTOR = ".job-item-search-result[data-job-id]"
MAX_PAGES_PER_RUN = 10


class SourceBlockedError(RuntimeError):
    pass


class TopCVScraper:
    def __init__(
        self,
        client: EthicalHttpClient | None = None,
        renderer: PageRenderer | None = None,
    ) -> None:
        self._external_client = client
        self._external_renderer = renderer

    async def scrape(self, max_pages: int = MAX_PAGES_PER_RUN) -> list[RawJobValidator]:
        if max_pages < 1 or max_pages > MAX_PAGES_PER_RUN:
            raise ValueError(f"max_pages must be between 1 and {MAX_PAGES_PER_RUN}")
        if self._external_client is not None:
            return await self._scrape(
                self._external_client,
                max_pages,
                self._external_renderer,
            )
        settings = get_settings()
        renderer = self._external_renderer or PlaywrightPageRenderer(
            settings.scraper_user_agent,
            settings.scraper_contact_email,
            allowed_hosts={"www.topcv.vn"},
        )
        async with EthicalHttpClient(settings.scraper_user_agent) as client:
            try:
                return await self._scrape(client, max_pages, renderer)
            finally:
                if self._external_renderer is None:
                    await renderer.close()

    @staticmethod
    async def _render(client: EthicalHttpClient, renderer: PageRenderer, url: str) -> str:
        await client.authorize(url)
        try:
            return await renderer.render(url, wait_for_selector=JOB_CARD_SELECTOR)
        except PageRenderError as exc:
            raise SourceBlockedError(
                "TopCV browser renderer did not receive public job cards"
            ) from exc

    async def _scrape(
        self,
        client: EthicalHttpClient,
        max_pages: int,
        renderer: PageRenderer | None,
    ) -> list[RawJobValidator]:
        jobs: dict[str, RawJobValidator] = {}
        available_pages = max_pages
        page = 1
        browser_required = False
        while page <= min(max_pages, available_pages):
            url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
            if browser_required:
                assert renderer is not None
                html = await self._render(client, renderer, url)
            else:
                try:
                    html = await client.get(url)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 403:
                        raise
                    if renderer is None:
                        raise SourceBlockedError(
                            "TopCV denied the declared research bot with HTTP 403"
                        ) from exc
                    html = await self._render(client, renderer, url)
                    browser_required = True
            page_jobs = parse_listing(html)
            if not page_jobs and not browser_required and renderer is not None:
                html = await self._render(client, renderer, url)
                page_jobs = parse_listing(html)
                browser_required = True
            if not page_jobs:
                raise SourceBlockedError(
                    "TopCV listing did not contain public job cards; collection stopped"
                )
            available_pages = listing_page_count(html)
            for job in page_jobs:
                jobs[job.platform_job_id] = job
            page += 1
        return list(jobs.values())
