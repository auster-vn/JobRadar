import asyncio
from datetime import UTC, datetime

from api.core.config import get_settings
from api.core.database import session_factory
from api.models import Company, Job, JobEmbedding


async def seed() -> None:
    if get_settings().app_env != "test":
        raise RuntimeError("CI seed is only allowed when APP_ENV=test")

    async with session_factory() as session:
        company = Company(name="CI Fixture", name_normalized="ci fixture")
        session.add(company)
        await session.flush()
        fixtures = (
            ("itviec", "Backend Engineer", "Backend Developer", ["Python", "PostgreSQL"]),
            ("topcv", "Machine Learning Engineer", "ML Engineer", ["Python", "PyTorch"]),
            ("vietnamworks", "Data Engineer", "Data Engineer", ["Python", "Spark"]),
        )
        jobs: list[Job] = []
        for platform, title, normalized_title, skills in fixtures:
            job = Job(
                platform=platform,
                platform_job_id=f"ci-{platform}-fixture-job",
                company_id=company.id,
                title=title,
                title_normalized=normalized_title,
                job_level="mid",
                location=["Ho Chi Minh City"],
                skills_required=skills,
                posted_at=datetime.now(UTC),
            )
            session.add(job)
            jobs.append(job)
        await session.flush()
        session.add(JobEmbedding(job_id=jobs[0].id, embedding=[0.1] * 384, model_name="ci-fixture"))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
