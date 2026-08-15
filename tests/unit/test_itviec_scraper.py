import pytest

from scrapers.itviec.scraper import MAX_PAGE_NUMBER, MAX_PAGES_PER_RUN, ITViecScraper


@pytest.mark.asyncio
async def test_scraper_rejects_page_count_outside_policy() -> None:
    scraper = ITViecScraper()

    with pytest.raises(ValueError, match=str(MAX_PAGES_PER_RUN)):
        await scraper.scrape(MAX_PAGES_PER_RUN + 1)

    with pytest.raises(ValueError, match=str(MAX_PAGE_NUMBER)):
        await scraper.scrape(2, start_page=MAX_PAGE_NUMBER)
