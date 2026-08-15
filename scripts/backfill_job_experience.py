import asyncio

from api.core.database import engine
from api.services.job_experience_backfill import backfill_job_experience


async def main() -> None:
    result = await backfill_job_experience()
    print(result)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
