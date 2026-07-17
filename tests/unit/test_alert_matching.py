from decimal import Decimal

from api.models import Job, JobAlert
from workers.alert_tasks import job_matches


def test_job_matches_all_alert_constraints() -> None:
    alert = JobAlert(
        required_skills=["Python", "FastAPI"],
        skill_match_min_pct=Decimal("50"),
        min_salary=Decimal("30000000"),
        job_levels=["senior"],
        locations=["Ho Chi Minh"],
    )
    job = Job(
        platform="demo",
        platform_job_id="1",
        company_id=None,  # type: ignore[arg-type]
        title="Senior Backend Engineer",
        skills_required=["python", "PostgreSQL"],
        salary_max=Decimal("40000000"),
        job_level="senior",
        location=["Ho Chi Minh"],
    )

    assert job_matches(alert, job)


def test_job_rejected_when_skill_score_is_too_low() -> None:
    alert = JobAlert(
        required_skills=["Python", "FastAPI"],
        skill_match_min_pct=Decimal("75"),
    )
    job = Job(
        platform="demo",
        platform_job_id="2",
        company_id=None,  # type: ignore[arg-type]
        title="Backend Engineer",
        skills_required=["Python"],
        location=[],
    )

    assert not job_matches(alert, job)
