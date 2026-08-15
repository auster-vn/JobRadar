import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from nlp.experience_parser import parse_experience_years
from scrapers.common.validator import RawJobValidator

BASE_URL = "https://www.topcv.vn"


def _text(node: Tag | None) -> str:
    return " ".join(node.stripped_strings) if node else ""


def _canonical_url(value: str) -> str:
    parts = urlsplit(urljoin(BASE_URL, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _relative_posted_at(value: str, now: datetime) -> datetime:
    lowered = value.casefold()
    if "hôm nay" in lowered or "vừa" in lowered:
        return now
    match = re.search(r"(\d+)\s*(phút|giờ|ngày|tuần|tháng)", lowered)
    if not match:
        return now
    count = int(match.group(1))
    unit = match.group(2)
    if unit == "phút":
        return now - timedelta(minutes=count)
    if unit == "giờ":
        return now - timedelta(hours=count)
    if unit == "ngày":
        return now - timedelta(days=count)
    if unit == "tuần":
        return now - timedelta(weeks=count)
    return now - timedelta(days=30 * count)


def _job_url(card: Tag) -> str | None:
    node = card.select_one("h3.title a[href*='/viec-lam/']")
    href = node.get("href") if node else None
    return _canonical_url(href) if isinstance(href, str) else None


def _experience(value: str) -> tuple[int | None, int | None]:
    under = re.search(r"dưới\s+(\d+)\s*năm", value, re.I)
    if under:
        return 0, int(under.group(1))
    return parse_experience_years(value, allow_bare=True)


def parse_listing(html: str, *, now: datetime | None = None) -> list[RawJobValidator]:
    soup = BeautifulSoup(html, "html.parser")
    timestamp = now or datetime.now(UTC)
    jobs: list[RawJobValidator] = []
    for card in soup.select(".job-item-search-result[data-job-id]"):
        job_id = card.get("data-job-id")
        title_node = card.select_one("h3.title a[href*='/viec-lam/'] span")
        company_node = card.select_one(".company-name")
        source_url = _job_url(card)
        if (
            not isinstance(job_id, str)
            or not job_id.strip()
            or not title_node
            or not company_node
            or source_url is None
        ):
            continue

        logo = card.select_one(".avatar img")
        logo_url = logo.get("data-src") or logo.get("src") if logo else None
        locations = [
            re.sub(r"\s*\(mới\)\s*$", "", _text(node), flags=re.I)
            for node in card.select(".city-text")
            if _text(node)
        ]
        experience_text = _text(card.select_one("label.exp"))
        experience_min, experience_max = _experience(experience_text)
        posted_text = _text(card.select_one(".box-icon label.address"))
        jobs.append(
            RawJobValidator(
                platform="topcv",
                platform_job_id=job_id.strip(),
                source_url=source_url,
                title=_text(title_node),
                company_name=_text(company_node),
                company_logo_url=logo_url if isinstance(logo_url, str) else None,
                salary_text=_text(card.select_one("label.salary span")) or None,
                location=list(dict.fromkeys(locations)),
                job_type="full_time",
                posted_at=_relative_posted_at(posted_text, timestamp),
                experience_years_min=experience_min,
                experience_years_max=experience_max,
            )
        )
    return jobs


def listing_page_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    value = _text(soup.select_one("#job-listing-paginate-text"))
    match = re.search(r"/\s*(\d+)\s*trang", value, re.I)
    return max(1, int(match.group(1))) if match else 1
