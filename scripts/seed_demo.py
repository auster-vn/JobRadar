import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from api.core.database import session_factory
from api.models import Company, Job

COMPANIES = (
    ("Nexa Labs", "product"),
    ("CloudMosaic", "startup"),
    ("Viet Systems", "enterprise"),
    ("OrbitWorks", "outsource"),
    ("DataSpring", "product"),
    ("PixelCraft", "agency"),
)
ROLES = (
    ("Backend Developer", "Python", 24, 42),
    ("Frontend Developer", "React", 22, 38),
    ("Data Engineer", "Spark", 28, 48),
    ("DevOps Engineer", "Kubernetes", 30, 52),
    ("QA Engineer", "Playwright", 18, 32),
    ("ML Engineer", "PyTorch", 32, 58),
    ("Mobile Developer", "Flutter", 24, 43),
    ("Product Manager", "System Design", 30, 50),
)
LOCATIONS = ("Ho Chi Minh", "Ha Noi", "Da Nang", "Remote")
LEVELS = ("junior", "mid", "senior", "lead")


async def seed() -> None:
    async with session_factory() as session, session.begin():
        await session.execute(delete(Job).where(Job.platform == "demo"))
        company_rows: list[Company] = []
        for name, company_type in COMPANIES:
            normalized = name.lower().replace(" ", "-")
            company = Company(
                id=uuid.uuid5(uuid.NAMESPACE_DNS, f"jobradar-demo-{normalized}"),
                name=name,
                name_normalized=normalized,
                company_type=company_type,
            )
            await session.merge(company)
            company_rows.append(company)
        await session.flush()

        now = datetime.now(UTC)
        for index in range(64):
            role, primary_skill, low, high = ROLES[index % len(ROLES)]
            company = company_rows[index % len(company_rows)]
            level = LEVELS[(index // len(ROLES)) % len(LEVELS)]
            level_factor = {"junior": 0.75, "mid": 1.0, "senior": 1.35, "lead": 1.6}[level]
            location = LOCATIONS[index % len(LOCATIONS)]
            title = role if level == "mid" else f"{level.title()} {role}"
            session.add(
                Job(
                    id=uuid.uuid5(uuid.NAMESPACE_DNS, f"jobradar-demo-job-{index}"),
                    platform="demo",
                    platform_job_id=f"demo-{index:03d}",
                    source_url=None,
                    company_id=company.id,
                    title=title,
                    title_normalized=title,
                    job_level=level,
                    job_type="remote" if location == "Remote" else "full_time",
                    location=[location],
                    salary_min=int(low * level_factor * 1_000_000),
                    salary_max=int(high * level_factor * 1_000_000),
                    salary_negotiable=False,
                    salary_currency="VND",
                    description_cleaned=(
                        f"Build production-grade {role.lower()} systems with {primary_skill}. "
                        "Work with a senior product team and own measurable delivery outcomes."
                    ),
                    skills_required=[primary_skill, "Git", "Docker", "REST API"],
                    skills_nice_to_have=["Kubernetes", "AWS"],
                    experience_years_min=max(0, LEVELS.index(level) * 2),
                    experience_years_max=LEVELS.index(level) * 2 + 3,
                    posted_at=now - timedelta(days=index % 31, hours=index % 12),
                    is_active=True,
                )
            )
    print("Seeded 64 clearly labeled demo jobs.")


if __name__ == "__main__":
    asyncio.run(seed())
