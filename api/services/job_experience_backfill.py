from sqlalchemy import select

from api.core.database import session_factory
from api.models import Job
from nlp.experience_parser import parse_experience_years


async def backfill_job_experience() -> dict[str, int]:
    scanned = 0
    updated = 0
    async with session_factory() as session, session.begin():
        jobs = list(
            await session.scalars(
                select(Job).where(
                    Job.experience_years_min.is_(None),
                    Job.description_cleaned.is_not(None),
                )
            )
        )
        for job in jobs:
            scanned += 1
            minimum, maximum = parse_experience_years(job.description_cleaned)
            if minimum is None:
                continue
            job.experience_years_min = minimum
            job.experience_years_max = maximum
            updated += 1
    return {"scanned": scanned, "updated": updated}
