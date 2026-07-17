from typing import Any, cast

import pytest

from scrapers.common.http_client import EthicalHttpClient
from scrapers.vietnamworks.scraper import LISTING_URL, SEARCH_URL, VietnamWorksScraper


class FakeClient:
    def __init__(self) -> None:
        self.pages: list[int] = []

    async def get(self, url: str, *, use_cache: bool = True) -> str:
        assert url == LISTING_URL
        return "<html></html>"

    async def post_json(
        self,
        url: str,
        payload: dict[str, object],
        *,
        policy_url: str,
        use_cache: bool = True,
    ) -> Any:
        assert url == SEARCH_URL
        assert policy_url == LISTING_URL
        page = cast(int, payload["page"])
        self.pages.append(page)
        return {
            "meta": {"code": 200, "nbPages": 3},
            "data": [
                {
                    "jobId": 100 + min(page, 1),
                    "jobTitle": "Backend Developer",
                    "companyName": "Example Co",
                    "isSalaryVisible": False,
                    "salaryCurrency": "VND",
                    "approvedOn": "2026-07-01T08:00:00+07:00",
                    "expiredOn": "2026-08-01T08:00:00+07:00",
                }
            ],
        }


@pytest.mark.asyncio
async def test_scraper_paginates_and_deduplicates_source_ids() -> None:
    client = FakeClient()
    scraper = VietnamWorksScraper(cast(EthicalHttpClient, client))
    jobs = await scraper.scrape(max_pages=3)
    assert client.pages == [0, 1, 2]
    assert [job.platform_job_id for job in jobs] == ["100", "101"]


@pytest.mark.asyncio
async def test_scraper_rejects_page_limit_above_policy_cap() -> None:
    scraper = VietnamWorksScraper(cast(EthicalHttpClient, FakeClient()))
    with pytest.raises(ValueError, match="between 1 and 10"):
        await scraper.scrape(max_pages=11)
