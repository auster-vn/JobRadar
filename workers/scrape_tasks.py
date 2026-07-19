import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from api.core.config import get_settings
from api.core.database import session_factory
from api.models import Company, Job, RawJob, ScrapeBatch
from nlp.location_normalizer import normalize_locations
from nlp.salary_parser import parse_salary
from nlp.skill_extractor import extract_skills
from nlp.title_normalizer import normalize_title
from scrapers.common.validator import RawJobValidator
from scrapers.itviec.scraper import ITViecScraper
from scrapers.topcv.scraper import TopCVScraper
from scrapers.vietnamworks.scraper import VietnamWorksScraper
from workers.async_runner import run_async
from workers.celery_app import app


def _normalize_company(value: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


async def _upsert_job(item: RawJobValidator) -> tuple[uuid.UUID, bool]:
    raw_payload = item.model_dump(mode="json")
    title = normalize_title(item.title)
    job_level = item.job_level or title.level
    salary = parse_salary(item.salary_text)
    extracted = extract_skills(" ".join([item.title, item.description or "", *item.skills]))
    required_skills = sorted({*item.skills, *extracted.required})
    normalized_company = _normalize_company(item.company_name)
    normalized_locations = normalize_locations(item.location)

    async with session_factory() as session, session.begin():
        existing_id = await session.scalar(
            select(Job.id).where(
                Job.platform == item.platform,
                Job.platform_job_id == item.platform_job_id,
            )
        )
        company_id = await session.scalar(
            insert(Company)
            .values(
                name=item.company_name,
                name_normalized=normalized_company,
                logo_url=str(item.company_logo_url) if item.company_logo_url else None,
            )
            .on_conflict_do_update(
                index_elements=[Company.name_normalized],
                set_={
                    "name": item.company_name,
                    "logo_url": str(item.company_logo_url) if item.company_logo_url else None,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(Company.id)
        )
        raw_id = await session.scalar(
            insert(RawJob)
            .values(
                platform=item.platform,
                platform_job_id=item.platform_job_id,
                raw_json=raw_payload,
                scraped_at=item.scraped_at,
                processed=True,
            )
            .on_conflict_do_update(
                constraint="uq_raw_job_source_id",
                set_={"raw_json": raw_payload, "scraped_at": item.scraped_at, "processed": True},
            )
            .returning(RawJob.id)
        )
        assert company_id is not None and raw_id is not None
        job_statement = insert(Job).values(
            raw_job_id=raw_id,
            platform=item.platform,
            platform_job_id=item.platform_job_id,
            source_url=str(item.source_url),
            company_id=company_id,
            title=item.title,
            title_normalized=title.title,
            job_level=job_level,
            job_type=item.job_type,
            location=normalized_locations,
            salary_min=salary.min_vnd,
            salary_max=salary.max_vnd,
            salary_negotiable=salary.negotiable,
            salary_currency="VND",
            description_raw=item.description,
            description_cleaned=item.description,
            skills_required=required_skills,
            skills_nice_to_have=extracted.nice_to_have,
            experience_years_min=item.experience_years_min,
            experience_years_max=item.experience_years_max,
            posted_at=item.posted_at,
            expires_at=item.expires_at,
            is_active=True,
        )
        incoming_salary_disclosed = or_(
            job_statement.excluded.salary_min.is_not(None),
            job_statement.excluded.salary_max.is_not(None),
        )
        job_id = await session.scalar(
            job_statement.on_conflict_do_update(
                constraint="uq_job_source_id",
                set_={
                    "raw_job_id": raw_id,
                    "source_url": str(item.source_url),
                    "company_id": company_id,
                    "title": item.title,
                    "title_normalized": title.title,
                    "job_level": job_level,
                    "job_type": item.job_type,
                    "location": normalized_locations,
                    "salary_min": case(
                        (incoming_salary_disclosed, job_statement.excluded.salary_min),
                        else_=Job.salary_min,
                    ),
                    "salary_max": case(
                        (incoming_salary_disclosed, job_statement.excluded.salary_max),
                        else_=Job.salary_max,
                    ),
                    "salary_negotiable": case(
                        (incoming_salary_disclosed, job_statement.excluded.salary_negotiable),
                        else_=Job.salary_negotiable,
                    ),
                    "description_raw": item.description,
                    "description_cleaned": item.description,
                    "skills_required": required_skills,
                    "skills_nice_to_have": extracted.nice_to_have,
                    "experience_years_min": item.experience_years_min,
                    "experience_years_max": item.experience_years_max,
                    "posted_at": func.least(Job.posted_at, job_statement.excluded.posted_at),
                    "expires_at": item.expires_at,
                    "is_active": True,
                    "updated_at": datetime.now(UTC),
                },
            ).returning(Job.id)
        )
        assert job_id is not None
        return job_id, existing_id is None


async def ingest_itviec(pages: int, start_page: int = 1, detail_limit: int = 0) -> dict[str, Any]:
    settings = get_settings()
    if not settings.enable_itviec_scraper:
        return {"status": "disabled", "platform": "itviec", "jobs": 0}
    started = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        batch = ScrapeBatch(platform="itviec", started_at=started, status="running")
        session.add(batch)
        await session.flush()
        batch_id = batch.id
    jobs: list[RawJobValidator] = []
    new_count = 0
    processed_count = 0
    try:
        jobs = await ITViecScraper().scrape(
            pages,
            start_page,
            detail_limit=detail_limit,
        )
        for item in jobs:
            _, created = await _upsert_job(item)
            new_count += int(created)
            processed_count += 1
        async with session_factory() as session, session.begin():
            await session.execute(
                update(ScrapeBatch)
                .where(ScrapeBatch.id == batch_id)
                .values(
                    completed_at=datetime.now(UTC),
                    jobs_found=len(jobs),
                    jobs_new=new_count,
                    jobs_updated=len(jobs) - new_count,
                    status="completed",
                )
            )
        return {"status": "completed", "platform": "itviec", "jobs": len(jobs)}
    except Exception:
        async with session_factory() as session, session.begin():
            await session.execute(
                update(ScrapeBatch)
                .where(ScrapeBatch.id == batch_id)
                .values(
                    completed_at=datetime.now(UTC),
                    jobs_found=len(jobs),
                    jobs_new=new_count,
                    jobs_updated=processed_count - new_count,
                    errors=1,
                    status="failed",
                )
            )
        raise


async def ingest_vietnamworks(max_pages: int = 10) -> dict[str, Any]:
    if not get_settings().enable_vietnamworks_scraper:
        return {"status": "disabled", "platform": "vietnamworks", "jobs": 0}
    started = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        batch = ScrapeBatch(platform="vietnamworks", started_at=started, status="running")
        session.add(batch)
        await session.flush()
        batch_id = batch.id
    jobs: list[RawJobValidator] = []
    new_count = 0
    processed_count = 0
    try:
        jobs = await VietnamWorksScraper().scrape(max_pages=max_pages)
        for item in jobs:
            _, created = await _upsert_job(item)
            new_count += int(created)
            processed_count += 1
        async with session_factory() as session, session.begin():
            await session.execute(
                update(ScrapeBatch)
                .where(ScrapeBatch.id == batch_id)
                .values(
                    completed_at=datetime.now(UTC),
                    jobs_found=len(jobs),
                    jobs_new=new_count,
                    jobs_updated=len(jobs) - new_count,
                    status="completed",
                )
            )
        return {"status": "completed", "platform": "vietnamworks", "jobs": len(jobs)}
    except Exception:
        async with session_factory() as session, session.begin():
            await session.execute(
                update(ScrapeBatch)
                .where(ScrapeBatch.id == batch_id)
                .values(
                    completed_at=datetime.now(UTC),
                    jobs_found=len(jobs),
                    jobs_new=new_count,
                    jobs_updated=processed_count - new_count,
                    errors=1,
                    status="failed",
                )
            )
        raise


async def ingest_topcv(max_pages: int = 10) -> dict[str, Any]:
    if not get_settings().enable_topcv_scraper:
        return {"status": "disabled", "platform": "topcv", "jobs": 0}
    started = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        batch = ScrapeBatch(platform="topcv", started_at=started, status="running")
        session.add(batch)
        await session.flush()
        batch_id = batch.id
    jobs: list[RawJobValidator] = []
    new_count = 0
    processed_count = 0
    try:
        jobs = await TopCVScraper().scrape(max_pages=max_pages)
        for item in jobs:
            _, created = await _upsert_job(item)
            new_count += int(created)
            processed_count += 1
        async with session_factory() as session, session.begin():
            await session.execute(
                update(ScrapeBatch)
                .where(ScrapeBatch.id == batch_id)
                .values(
                    completed_at=datetime.now(UTC),
                    jobs_found=len(jobs),
                    jobs_new=new_count,
                    jobs_updated=len(jobs) - new_count,
                    status="completed",
                )
            )
        return {"status": "completed", "platform": "topcv", "jobs": len(jobs)}
    except Exception:
        async with session_factory() as session, session.begin():
            await session.execute(
                update(ScrapeBatch)
                .where(ScrapeBatch.id == batch_id)
                .values(
                    completed_at=datetime.now(UTC),
                    jobs_found=len(jobs),
                    jobs_new=new_count,
                    jobs_updated=processed_count - new_count,
                    errors=1,
                    status="failed",
                )
            )
        raise


@app.task(name="workers.scrape_tasks.scrape_itviec")
def scrape_itviec(pages: int = 25, start_page: int = 1, detail_limit: int = 25) -> dict[str, Any]:
    return run_async(ingest_itviec(pages, start_page, detail_limit))


@app.task(name="workers.scrape_tasks.scrape_vietnamworks")
def scrape_vietnamworks(max_pages: int = 10) -> dict[str, Any]:
    return run_async(ingest_vietnamworks(max_pages=max_pages))


@app.task(name="workers.scrape_tasks.scrape_topcv")
def scrape_topcv(max_pages: int = 10) -> dict[str, Any]:
    return run_async(ingest_topcv(max_pages=max_pages))


@app.task(name="workers.scrape_tasks.mark_expired_jobs")
def mark_expired_jobs() -> dict[str, int]:
    async def expire() -> int:
        async with session_factory() as session, session.begin():
            result = await session.execute(
                update(Job)
                .where(
                    Job.is_active.is_(True),
                    Job.posted_at < datetime.now(UTC) - timedelta(days=60),
                )
                .values(is_active=False, updated_at=datetime.now(UTC))
            )
            return result.rowcount  # type: ignore[attr-defined, no-any-return]

    return {"expired": run_async(expire())}
