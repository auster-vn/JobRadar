import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from scrapers.common.validator import RawJobValidator

BASE_URL = "https://itviec.com"


def _text(node: Tag | None) -> str:
    return " ".join(node.stripped_strings) if node else ""


def _relative_posted_at(value: str, now: datetime) -> datetime:
    lowered = value.lower()
    match = re.search(r"(\d+)\s+(minute|hour|day|week|month)", lowered)
    if not match:
        return now
    count = int(match.group(1))
    unit = match.group(2)
    if unit == "minute":
        return now - timedelta(minutes=count)
    if unit == "hour":
        return now - timedelta(hours=count)
    if unit == "day":
        return now - timedelta(days=count)
    if unit == "week":
        return now - timedelta(weeks=count)
    return now - timedelta(days=30 * count)


def parse_listing(html: str, *, now: datetime | None = None) -> list[RawJobValidator]:
    soup = BeautifulSoup(html, "html.parser")
    timestamp = now or datetime.now(UTC)
    results: list[RawJobValidator] = []
    for card in soup.select("div.job-card[data-job-key]"):
        key = card.get("data-job-key")
        title_node = card.select_one("[data-search--job-selection-target='jobTitle']")
        company_node = card.select_one("a[href^='/companies/']:not(.logo-employer-card)")
        if not isinstance(key, str) or not title_node or not company_node:
            continue
        source_path = title_node.get("data-url") or card.get(
            "data-search--job-selection-job-url-value"
        )
        if not isinstance(source_path, str):
            continue
        source_url = urljoin(BASE_URL, source_path.split("/content?")[0])
        logo = card.select_one("a.logo-employer-card img")
        logo_url = logo.get("data-src") if logo else None
        locations: list[str] = []
        for node in card.select("div[title]"):
            title = node.get("title")
            known_locations = ("Minh", "Noi", "Da Nang")
            if isinstance(title, str) and any(place in title for place in known_locations):
                locations = [part.strip() for part in title.split(" - ")]
                break
        skills = [
            _text(tag)
            for tag in card.select("[data-responsive-tag-list-target='tag']")
            if _text(tag)
        ]
        salary_node = card.select_one(".salary")
        posted_node = card.find(string=re.compile(r"Posted", re.I))
        posted_context = _text(posted_node.parent if posted_node and posted_node.parent else None)
        results.append(
            RawJobValidator(
                platform="itviec",
                platform_job_id=key,
                source_url=source_url,
                title=_text(title_node),
                company_name=_text(company_node),
                company_logo_url=logo_url if isinstance(logo_url, str) else None,
                description=_text(card.select_one("ul")),
                salary_text=_text(salary_node),
                location=locations,
                job_type="remote" if "remote" in _text(card).lower() else "full_time",
                skills=skills,
                posted_at=_relative_posted_at(posted_context, timestamp),
            )
        )
    return results


def platform_slug(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    if not slug:
        raise ValueError(f"cannot derive job slug from URL: {url}")
    return slug


def enrich_from_detail(job: RawJobValidator, html: str) -> RawJobValidator:
    soup = BeautifulSoup(html, "html.parser")
    payload: dict[str, object] | None = None
    for script in soup.select("script[type='application/ld+json']"):
        try:
            candidate = json.loads(script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(candidate, dict) and candidate.get("@type") == "JobPosting":
            payload = candidate
            break
    if payload is None:
        return job

    description_html = payload.get("description")
    description = (
        "\n".join(BeautifulSoup(description_html, "html.parser").stripped_strings)
        if isinstance(description_html, str)
        else job.description
    )
    raw_skills = payload.get("skills")
    detail_skills = (
        [skill.strip() for skill in raw_skills.split(",") if skill.strip()]
        if isinstance(raw_skills, str)
        else []
    )
    expires_at: datetime | None = None
    valid_through = payload.get("validThrough")
    if isinstance(valid_through, str):
        try:
            expires_at = datetime.fromisoformat(valid_through).replace(tzinfo=UTC)
        except ValueError:
            expires_at = None
    experience_years_min: int | None = None
    experience = payload.get("experienceRequirements")
    if isinstance(experience, dict):
        months = experience.get("monthsOfExperience")
        if isinstance(months, int | float) and months >= 0:
            experience_years_min = int(months // 12)

    return job.model_copy(
        update={
            "description": description,
            "skills": sorted({*job.skills, *detail_skills}),
            "expires_at": expires_at,
            "experience_years_min": experience_years_min,
        }
    )
