from sqlalchemy import select

from api.core.database import session_factory
from api.models import Job
from nlp.location_normalizer import normalize_locations


async def backfill_job_locations() -> dict[str, int]:
    scanned = 0
    updated = 0
    async with session_factory() as session, session.begin():
        jobs = list(await session.scalars(select(Job)))
        for job in jobs:
            scanned += 1
            normalized = normalize_locations(job.location)
            if job.location == normalized:
                continue
            job.location = normalized
            updated += 1
    return {"scanned": scanned, "updated": updated}
