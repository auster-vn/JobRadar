import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from api.core.database import session_factory
from scrapers.common.validator import RawJobValidator
from workers.scrape_tasks import _upsert_job


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repeat_scrape_cannot_erase_disclosed_salary_or_move_posting_forward() -> None:
    source_id = f"integration-{uuid.uuid4().hex}"
    company_name = f"Integration Salary {uuid.uuid4().hex}"
    posted_at = datetime(2026, 7, 1, 8, tzinfo=UTC)
    first = RawJobValidator(
        platform="vietnamworks",
        platform_job_id=source_id,
        source_url=f"https://www.vietnamworks.com/jobs/{source_id}",
        title="Backend Developer",
        company_name=company_name,
        description="Build and operate Python services in a production environment.",
        salary_text="20 - 30 trieu",
        location=["Ha Noi"],
        job_type="full_time",
        job_level="mid",
        skills=["Python", "PostgreSQL"],
        posted_at=posted_at,
        scraped_at=posted_at + timedelta(hours=1),
    )
    hidden_salary = RawJobValidator(
        platform="vietnamworks",
        platform_job_id=source_id,
        source_url=f"https://www.vietnamworks.com/jobs/{source_id}",
        title="Backend Engineer",
        company_name=company_name,
        description="Build and operate Python services in a production environment.",
        salary_text=None,
        location=["Ha Noi"],
        job_type="full_time",
        job_level="mid",
        skills=["Python", "PostgreSQL"],
        posted_at=posted_at + timedelta(days=2),
        scraped_at=posted_at + timedelta(days=2, hours=1),
    )

    job_id: uuid.UUID | None = None
    try:
        job_id, created = await _upsert_job(first)
        repeated_id, repeated_created = await _upsert_job(hidden_salary)

        assert created is True
        assert repeated_created is False
        assert repeated_id == job_id
        async with session_factory() as session:
            result = await session.execute(
                text(
                    """
                        SELECT salary_min, salary_max, salary_negotiable, posted_at,
                          title, company_id, raw_job_id
                        FROM jobs
                        WHERE id = :job_id
                    """
                ),
                {"job_id": job_id},
            )
            row = result.mappings().one()

        assert row["salary_min"] == Decimal("20000000")
        assert row["salary_max"] == Decimal("30000000")
        assert row["salary_negotiable"] is False
        assert row["posted_at"] == posted_at
        assert row["title"] == "Backend Engineer"
    finally:
        if job_id is not None:
            async with session_factory() as session, session.begin():
                result = await session.execute(
                    text("DELETE FROM jobs WHERE id = :job_id RETURNING company_id, raw_job_id"),
                    {"job_id": job_id},
                )
                deleted = result.mappings().one_or_none()
                if deleted is not None:
                    await session.execute(
                        text("DELETE FROM raw_jobs WHERE id = :raw_job_id"),
                        {"raw_job_id": deleted["raw_job_id"]},
                    )
                    await session.execute(
                        text("DELETE FROM companies WHERE id = :company_id"),
                        {"company_id": deleted["company_id"]},
                    )
