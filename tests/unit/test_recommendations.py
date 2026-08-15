import uuid
from datetime import UTC, datetime
from decimal import Decimal

from api.models import Job, UserProfile
from api.services.recommendations import _rank_jobs


def _job(job_id: uuid.UUID, skills: list[str]) -> Job:
    return Job(
        id=job_id,
        platform="test",
        platform_job_id=str(job_id),
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        location=["Ha Noi"],
        skills_required=skills,
        salary_min=Decimal("20000000"),
        salary_max=Decimal("30000000"),
        salary_currency="VND",
        salary_negotiable=False,
        is_active=True,
        posted_at=datetime.now(UTC),
    )


def test_daily_recommendations_are_ranked_bounded_and_thresholded() -> None:
    profile = UserProfile(
        user_id=uuid.uuid4(),
        skills=["Python", "PostgreSQL"],
        experience_years=4,
        preferred_locations=["Ha Noi"],
    )
    strong = _job(uuid.uuid4(), ["Python", "PostgreSQL"])
    medium = _job(uuid.uuid4(), ["Python", "Go"])
    weak = _job(uuid.uuid4(), ["Java", "Kotlin"])

    ranked = _rank_jobs([weak, medium, strong], profile, minimum_score=55, limit=2)

    assert [job.id for _, job in ranked] == [strong.id, medium.id]
    assert all(score.overall_score >= 55 for score, _ in ranked)
