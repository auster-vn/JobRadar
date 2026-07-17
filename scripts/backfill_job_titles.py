import asyncio

from api.core.database import engine
from api.services.job_title_backfill import backfill_job_titles


async def main() -> None:
    result = await backfill_job_titles()
    print(result)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
