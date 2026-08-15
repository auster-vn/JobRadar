from api.core.config import get_settings
from scrapers.common.http_client import EthicalHttpClient
from scrapers.common.validator import RawJobValidator
from scrapers.vietnamworks.parser import parse_search_response

LISTING_URL = "https://www.vietnamworks.com/it-phan-mem-kv"
SEARCH_URL = "https://ms.vietnamworks.com/job-search/v1.0/search"
MAX_PAGES_PER_RUN = 10
HITS_PER_PAGE = 50
RETRIEVE_FIELDS = [
    "jobTitle",
    "salaryMax",
    "isSalaryVisible",
    "salaryMin",
    "salaryCurrency",
    "companyLogo",
    "jobLevel",
    "jobLevelId",
    "jobId",
    "approvedOn",
    "expiredOn",
    "workingLocations",
    "companyName",
    "skills",
    "jobDescription",
    "jobRequirement",
    "prettySalary",
    "typeWorkingId",
]


class VietnamWorksScraper:
    def __init__(self, client: EthicalHttpClient | None = None) -> None:
        self._external_client = client

    @staticmethod
    def _payload(page: int) -> dict[str, object]:
        return {
            "userId": 0,
            "query": "it phan mem",
            "filter": [],
            "ranges": [],
            "order": [],
            "hitsPerPage": HITS_PER_PAGE,
            "page": page,
            "retrieveFields": RETRIEVE_FIELDS,
            "summaryVersion": "",
        }

    async def _scrape(self, client: EthicalHttpClient, max_pages: int) -> list[RawJobValidator]:
        # This GET proves the public search route remains robots-permitted before
        # using the first-party JSON endpoint that renders that same route.
        await client.get(LISTING_URL)
        jobs: dict[str, RawJobValidator] = {}
        page = 0
        available_pages = max_pages
        while page < min(max_pages, available_pages):
            payload = await client.post_json(
                SEARCH_URL,
                self._payload(page),
                policy_url=LISTING_URL,
            )
            page_jobs, available_pages = parse_search_response(payload)
            for job in page_jobs:
                jobs[job.platform_job_id] = job
            if not page_jobs:
                break
            page += 1
        return list(jobs.values())

    async def scrape(self, max_pages: int = MAX_PAGES_PER_RUN) -> list[RawJobValidator]:
        if max_pages < 1 or max_pages > MAX_PAGES_PER_RUN:
            raise ValueError(f"max_pages must be between 1 and {MAX_PAGES_PER_RUN}")
        if self._external_client is not None:
            return await self._scrape(self._external_client, max_pages)
        settings = get_settings()
        async with EthicalHttpClient(settings.scraper_user_agent) as client:
            return await self._scrape(client, max_pages)
