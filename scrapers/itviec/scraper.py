from api.core.config import get_settings
from scrapers.common.http_client import EthicalHttpClient
from scrapers.common.validator import RawJobValidator
from scrapers.itviec.parser import enrich_from_detail, parse_listing

LISTING_URL = "https://itviec.com/it-jobs"
MAX_PAGES_PER_RUN = 25
MAX_PAGE_NUMBER = 50


class ITViecScraper:
    def __init__(self, client: EthicalHttpClient | None = None) -> None:
        self._external_client = client

    async def scrape(
        self,
        pages: int = 1,
        start_page: int = 1,
        *,
        detail_limit: int = 0,
    ) -> list[RawJobValidator]:
        if pages < 1 or pages > MAX_PAGES_PER_RUN:
            raise ValueError(f"pages must be between 1 and {MAX_PAGES_PER_RUN}")
        if start_page < 1 or start_page + pages - 1 > MAX_PAGE_NUMBER:
            raise ValueError(f"requested page range must stay between 1 and {MAX_PAGE_NUMBER}")
        if self._external_client:
            jobs = await self._scrape_pages(self._external_client, pages, start_page)
            return await self._enrich_details(self._external_client, jobs, detail_limit)
        settings = get_settings()
        async with EthicalHttpClient(settings.scraper_user_agent) as client:
            jobs = await self._scrape_pages(client, pages, start_page)
            return await self._enrich_details(client, jobs, detail_limit)

    async def _scrape_pages(
        self, client: EthicalHttpClient, pages: int, start_page: int
    ) -> list[RawJobValidator]:
        jobs: dict[str, RawJobValidator] = {}
        for page in range(start_page, start_page + pages):
            separator = "?" if page == 1 else "?page="
            url = LISTING_URL if page == 1 else f"{LISTING_URL}{separator}{page}"
            html = await client.get(url)
            for job in parse_listing(html):
                jobs[job.platform_job_id] = job
        return list(jobs.values())

    async def _enrich_details(
        self,
        client: EthicalHttpClient,
        jobs: list[RawJobValidator],
        limit: int,
    ) -> list[RawJobValidator]:
        if limit < 0 or limit > 100:
            raise ValueError("detail_limit must be between 0 and 100")
        for index, job in enumerate(jobs[:limit]):
            jobs[index] = enrich_from_detail(job, await client.get(str(job.source_url)))
        return jobs
