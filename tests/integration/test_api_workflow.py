import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text

from api.core.database import session_factory
from api.main import app
from api.models import UserProfile
from api.services.job_experience_backfill import backfill_job_experience
from api.services.job_title_backfill import backfill_job_titles
from api.services.profile_security import load_cv_text, set_profile_owner
from api.services.salary_observation_import import import_salary_observations
from scrapers.common.validator import RawJobValidator
from workers.scrape_tasks import _upsert_job


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_authenticated_user_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    embedded_profiles: list[str] = []
    monkeypatch.setattr(
        "api.routers.profile.embed_profile.delay", lambda user_id: embedded_profiles.append(user_id)
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 200
        assert (await client.get("/api/jobs?limit=5")).status_code == 200
        topcv_jobs = await client.get("/api/jobs?platform=topcv&limit=5")
        assert topcv_jobs.status_code == 200
        assert topcv_jobs.json()["data"]
        assert all(job["platform"] == "topcv" for job in topcv_jobs.json()["data"])
        assert (await client.get("/api/jobs?platform=unsupported")).status_code == 422
        jobs = (await client.get("/api/jobs?limit=1")).json()["data"]
        assert (await client.get("/api/jobs/trending?limit=5")).status_code == 200
        if jobs:
            similar = await client.get(f"/api/jobs/{jobs[0]['id']}/similar?limit=3")
            assert similar.status_code == 200
        for endpoint in (
            "/api/salary/benchmark/Backend%20Developer",
            "/api/analytics/skills/trending",
            "/api/analytics/hiring/trends",
            "/api/analytics/salary/by-skill",
            "/api/analytics/salary/by-company-type",
        ):
            assert (await client.get(endpoint)).status_code == 200
        anonymous_session = await client.get("/api/auth/session")
        assert anonymous_session.status_code == 200
        assert anonymous_session.json() is None
        assert (await client.get("/api/admin/pipeline/status")).status_code == 401
        admin = await client.get(
            "/api/admin/pipeline/status",
            headers={"X-Admin-Key": "development-admin-key"},
        )
        assert admin.status_code == 200
        assert admin.json()["normalized_jobs"] >= 1
        readiness = await client.get(
            "/api/admin/ml/data-readiness",
            headers={"X-Admin-Key": "development-admin-key"},
        )
        assert readiness.status_code == 200
        readiness_body = readiness.json()
        assert isinstance(readiness_body["ready"], bool)
        assert readiness_body["sample_size"] >= 1
        assert len(readiness_body["requirements"]) == 6

        email = f"integration-{uuid.uuid4()}@example.com"
        registered = await client.post(
            "/api/auth/register",
            json={"email": email, "password": "A-strong-test-password-123"},
        )
        assert registered.status_code == 201
        assert (await client.get("/api/auth/me")).status_code == 200
        assert (await client.get("/api/auth/session")).json()["email"] == email

        cv_plaintext = "Backend engineer with Python FastAPI PostgreSQL Docker experience."
        cv = await client.post(
            "/api/profile/cv",
            files={
                "file": (
                    "cv.txt",
                    cv_plaintext.encode(),
                    "text/plain",
                )
            },
        )
        assert cv.status_code == 200
        assert "Python" in cv.json()["skills"]
        assert cv.json()["has_cv"] is True
        assert embedded_profiles == [cv.json()["user_id"]]

        user_id = uuid.UUID(cv.json()["user_id"])
        async with session_factory() as security_session:
            await set_profile_owner(security_session, user_id)
            profile = await security_session.get(UserProfile, user_id)
            assert profile is not None
            assert isinstance(profile.cv_text_encrypted, bytes)
            assert cv_plaintext.encode() not in profile.cv_text_encrypted
            assert await load_cv_text(security_session, user_id) == cv_plaintext

        deleted_cv = await client.delete("/api/profile/cv")
        assert deleted_cv.status_code == 200
        assert deleted_cv.json()["has_cv"] is False
        profile_after_delete = await client.get("/api/profile")
        assert profile_after_delete.json()["has_cv"] is False
        async with session_factory() as security_session:
            await set_profile_owner(security_session, user_id)
            profile = await security_session.get(UserProfile, user_id)
            assert profile is not None and profile.cv_text_encrypted is None

        created = await client.post(
            "/api/alerts",
            json={
                "name": "Python backend",
                "required_skills": ["Python"],
                "job_levels": [],
                "locations": [],
                "skill_match_min_pct": 50,
                "channel": "email",
                "is_active": True,
            },
        )
        assert created.status_code == 201
        alert_id = created.json()["id"]
        history = await client.get(f"/api/alerts/{alert_id}/history")
        assert history.status_code == 200
        assert history.json() == []


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_salary_observation_import_updates_corrected_source_rows() -> None:
    record_id = uuid.uuid4().hex
    base: dict[str, object] = {
        "source": "integration_test",
        "source_record_id": record_id,
        "source_snapshot_date": date(2026, 1, 1),
        "title": "Backend Developer",
        "title_normalized": "Backend Developer",
        "job_level": "mid",
        "location": "Ha Noi",
        "experience_years_min": 6,
        "experience_years_max": 6,
        "skills": ["Python"],
        "salary_min": Decimal("20000000"),
        "salary_max": Decimal("30000000"),
        "category": "technology",
        "source_metadata": {
            "dataset": "integration-fixture",
            "dataset_commit": "revision-1",
            "license": "test-only",
        },
    }
    try:
        assert await import_salary_observations([base]) == 1
        assert (
            await import_salary_observations(
                [
                    {
                        **base,
                        "experience_years_min": 0,
                        "experience_years_max": 0,
                        "source_metadata": {
                            "dataset": "integration-fixture",
                            "dataset_commit": "revision-2",
                            "license": "test-only",
                        },
                    }
                ]
            )
            == 1
        )

        async with session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT experience_years_min, experience_years_max, source_metadata
                    FROM salary_observations
                    WHERE source = 'integration_test' AND source_record_id = :record_id
                    """
                ),
                {"record_id": record_id},
            )
            row = result.mappings().one()
            assert row["experience_years_min"] == 0
            assert row["experience_years_max"] == 0
            assert row["source_metadata"] == {
                "dataset": "integration-fixture",
                "dataset_commit": "revision-2",
                "license": "test-only",
            }
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    """
                    DELETE FROM salary_observations
                    WHERE source = 'integration_test' AND source_record_id = :record_id
                    """
                ),
                {"record_id": record_id},
            )


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
async def test_job_metadata_backfills_are_idempotent() -> None:
    company_id = uuid.uuid4()
    job_id = uuid.uuid4()
    platform_job_id = f"integration-{job_id}"
    try:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO companies (id, name, name_normalized)
                    VALUES (:company_id, :name, :normalized)
                    """
                ),
                {
                    "company_id": company_id,
                    "name": f"Integration {company_id}",
                    "normalized": f"integration-{company_id}",
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO jobs (
                      id, platform, platform_job_id, company_id, title,
                      title_normalized, job_level, description_cleaned, location
                    ) VALUES (
                      :job_id, 'linkedin', :platform_job_id, :company_id,
                      'Trưởng Nhóm Backend', 'incorrect', 'mid',
                      'Yêu cầu tối thiểu 5 năm kinh nghiệm phát triển API.',
                      ARRAY['Ha Noi']
                    )
                    """
                ),
                {
                    "job_id": job_id,
                    "platform_job_id": platform_job_id,
                    "company_id": company_id,
                },
            )

        assert (await backfill_job_experience())["updated"] >= 1
        assert (await backfill_job_titles())["updated"] >= 1
        assert (await backfill_job_experience())["updated"] == 0
        assert (await backfill_job_titles())["updated"] == 0

        async with session_factory() as session:
            row = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT title_normalized, job_level,
                          experience_years_min, experience_years_max
                        FROM jobs WHERE id = :job_id
                        """
                        ),
                        {"job_id": job_id},
                    )
                )
                .mappings()
                .one()
            )
            assert row == {
                "title_normalized": "Backend Developer",
                "job_level": "lead",
                "experience_years_min": 5,
                "experience_years_max": None,
            }
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(text("DELETE FROM jobs WHERE id = :job_id"), {"job_id": job_id})
            await session.execute(
                text("DELETE FROM companies WHERE id = :company_id"),
                {"company_id": company_id},
            )


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
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
