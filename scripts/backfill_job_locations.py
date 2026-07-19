import asyncio

from api.core.database import engine
from api.services.job_location_backfill import backfill_job_locations


async def main() -> None:
    result = await backfill_job_locations()
    print(result)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
