import httpx

from api.core.config import get_settings
from scrapers.common.http_client import EthicalHttpClient
from scrapers.common.validator import RawJobValidator
from scrapers.topcv.parser import listing_page_count, parse_listing

LISTING_URL = "https://www.topcv.vn/tim-viec-lam-software-engineering-cr257cb258"
MAX_PAGES_PER_RUN = 10


class SourceBlockedError(RuntimeError):
    pass


class TopCVScraper:
    def __init__(self, client: EthicalHttpClient | None = None) -> None:
        self._external_client = client

    async def scrape(self, max_pages: int = MAX_PAGES_PER_RUN) -> list[RawJobValidator]:
        if max_pages < 1 or max_pages > MAX_PAGES_PER_RUN:
            raise ValueError(f"max_pages must be between 1 and {MAX_PAGES_PER_RUN}")
        if self._external_client is not None:
            return await self._scrape(self._external_client, max_pages)
        settings = get_settings()
        async with EthicalHttpClient(settings.scraper_user_agent) as client:
            return await self._scrape(client, max_pages)

    async def _scrape(self, client: EthicalHttpClient, max_pages: int) -> list[RawJobValidator]:
        jobs: dict[str, RawJobValidator] = {}
        available_pages = max_pages
        page = 1
        while page <= min(max_pages, available_pages):
            url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
            try:
                html = await client.get(url)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 403:
                    raise SourceBlockedError(
                        "TopCV denied the declared research bot with HTTP 403"
                    ) from exc
                raise
            page_jobs = parse_listing(html)
            if not page_jobs:
                raise SourceBlockedError(
                    "TopCV listing did not contain public job cards; collection stopped"
                )
            available_pages = listing_page_count(html)
            for job in page_jobs:
                jobs[job.platform_job_id] = job
            page += 1
        return list(jobs.values())
