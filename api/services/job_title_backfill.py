from sqlalchemy import select

from api.core.database import session_factory
from api.models import Job
from nlp.title_normalizer import normalize_title


async def backfill_job_titles() -> dict[str, int]:
    scanned = 0
    updated = 0
    async with session_factory() as session, session.begin():
        jobs = list(await session.scalars(select(Job)))
        for job in jobs:
            scanned += 1
            normalized = normalize_title(job.title)
            if job.title_normalized == normalized.title and job.job_level == normalized.level:
                continue
            job.title_normalized = normalized.title
            job.job_level = normalized.level
            updated += 1
    return {"scanned": scanned, "updated": updated}
