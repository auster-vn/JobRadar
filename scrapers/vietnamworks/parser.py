import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from nlp.experience_parser import parse_experience_years
from scrapers.common.validator import JobLevel, RawJobValidator

STRUCTURED_JOB_LEVELS: dict[str, JobLevel] = {
    "Fresher/Entry level": "fresher",
    "Manager": "manager",
    "Director and above": "director",
}


def _structured_job_level(value: object) -> JobLevel | None:
    return STRUCTURED_JOB_LEVELS.get(value) if isinstance(value, str) else None


def _posted_at(value: str, now: datetime) -> datetime:
    lowered = value.lower()
    match = re.search(r"(\d+)\s+ngày", lowered)
    return now - timedelta(days=int(match.group(1))) if match else now


def _canonical_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")


def _api_datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"VietnamWorks search result is missing {field}")
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _text(value: object) -> str:
    return (
        BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
        if isinstance(value, str)
        else ""
    )


def _structured_salary(item: dict[str, Any]) -> str | None:
    if item.get("isSalaryVisible") is not True:
        return None
    currency = item.get("salaryCurrency")
    if currency not in {"VND", "USD"}:
        return None

    def amount(field: str) -> Decimal | None:
        value = item.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        parsed = Decimal(str(value))
        return parsed if parsed.is_finite() and parsed > 0 else None

    def display(value: Decimal) -> str:
        return format(value, "f").rstrip("0").rstrip(".") if value % 1 else format(value, "f")

    low = amount("salaryMin")
    high = amount("salaryMax")
    if low is None and high is None:
        return None
    multiplier = Decimal(25_000 if currency == "USD" else 1)
    converted = [value * multiplier for value in (low, high) if value is not None]
    if any(value < 1_000_000 or value > 200_000_000 for value in converted):
        return None
    if low is not None and high is not None:
        separator = " USD - " if currency == "USD" else " - "
        suffix = " USD" if currency == "USD" else " VND"
        return f"{display(low)}{separator}{display(high)}{suffix}"
    prefix = "Từ" if low is not None else "Lên đến"
    value = low if low is not None else high
    assert value is not None
    marker = " USD" if currency == "USD" else " VND"
    return f"{prefix} {display(value)}{marker}"


def parse_search_response(payload: object) -> tuple[list[RawJobValidator], int]:
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        raise ValueError("VietnamWorks search API returned an invalid envelope")
    meta: dict[str, Any] = payload["meta"]
    items = payload.get("data")
    if meta.get("code") != 200 or not isinstance(items, list):
        raise ValueError("VietnamWorks search API returned an unsuccessful response")
    pages = meta.get("nbPages")
    if not isinstance(pages, int) or pages < 0:
        raise ValueError("VietnamWorks search API returned an invalid page count")

    jobs: list[RawJobValidator] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("VietnamWorks search API returned a non-object job")
        job_id = item.get("jobId")
        title = item.get("jobTitle")
        company = item.get("companyName")
        if not isinstance(job_id, (int, str)) or not isinstance(title, str) or not title.strip():
            raise ValueError("VietnamWorks search result is missing job identity")
        if not isinstance(company, str) or not company.strip():
            raise ValueError("VietnamWorks search result is missing company name")
        locations = item.get("workingLocations") or []
        if not isinstance(locations, list):
            raise ValueError("VietnamWorks search result has invalid locations")
        city_names = [
            location["cityName"]
            for location in locations
            if isinstance(location, dict)
            and isinstance(location.get("cityName"), str)
            and location["cityName"].strip()
        ]
        skills = item.get("skills") or []
        if not isinstance(skills, list):
            raise ValueError("VietnamWorks search result has invalid skills")
        skill_names = [
            skill["skillName"]
            for skill in skills
            if isinstance(skill, dict)
            and isinstance(skill.get("skillName"), str)
            and skill["skillName"].strip()
        ]
        description = " ".join(
            part
            for part in (_text(item.get("jobDescription")), _text(item.get("jobRequirement")))
            if part
        )
        experience_min, experience_max = parse_experience_years(description)
        jobs.append(
            RawJobValidator(
                platform="vietnamworks",
                platform_job_id=str(job_id),
                source_url=f"https://www.vietnamworks.com/{_slug(title)}-{job_id}-jv",
                title=title.strip(),
                company_name=company.strip(),
                company_logo_url=item.get("companyLogo") or None,
                description=description or None,
                salary_text=_structured_salary(item),
                location=list(dict.fromkeys(city_names)),
                skills=list(dict.fromkeys(skill_names)),
                job_level=_structured_job_level(item.get("jobLevel")),
                experience_years_min=experience_min,
                experience_years_max=experience_max,
                posted_at=_api_datetime(item.get("approvedOn"), field="approvedOn"),
                expires_at=_api_datetime(item.get("expiredOn"), field="expiredOn"),
            )
        )
    return jobs, pages


def parse_listing(html: str, *, now: datetime | None = None) -> list[RawJobValidator]:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("#__NEXT_DATA__")
    if not node or not node.string:
        return []
    payload = json.loads(node.string)
    page = payload.get("props", {}).get("pageProps", {})
    timestamp = now or datetime.now(UTC)
    jobs: list[RawJobValidator] = []
    for item in page.get("outstandingJobs", []):
        url = _canonical_url(item["url"])
        match = re.search(r"-(\d+)-jv$", urlsplit(url).path)
        if not match:
            continue
        jobs.append(
            RawJobValidator(
                platform="vietnamworks",
                platform_job_id=match.group(1),
                source_url=url,
                title=item["jobTitle"],
                company_name=item["company"],
                company_logo_url=item.get("logoUrl"),
                salary_text=item.get("prettySalary") or item.get("salary"),
                location=[part.strip() for part in item.get("location", "").split(",") if part],
                posted_at=_posted_at(item.get("onlineOnText", ""), timestamp),
            )
        )
    return jobs
