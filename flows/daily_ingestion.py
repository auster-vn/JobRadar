import asyncio
from collections.abc import Callable
from typing import Any, cast

from workers.alert_tasks import evaluate_alerts
from workers.scrape_tasks import ingest_itviec, ingest_topcv, ingest_vietnamworks


async def run_daily_ingestion(pages: int = 20) -> dict[str, Any]:
    itviec, topcv, vietnamworks = await asyncio.gather(
        ingest_itviec(pages),
        ingest_topcv(),
        ingest_vietnamworks(),
    )
    alerts = await evaluate_alerts()
    return {
        "itviec": itviec,
        "topcv": topcv,
        "vietnamworks": vietnamworks,
        "alerts": alerts,
    }


def prefect_flow() -> Callable[..., Any]:
    """Build the Prefect flow only when the orchestration extra is installed."""
    from prefect import flow

    @flow(name="jobradar-daily-ingestion", log_prints=True)  # type: ignore[untyped-decorator]
    def daily_ingestion(pages: int = 20) -> dict[str, Any]:
        return asyncio.run(run_daily_ingestion(pages))

    return cast(Callable[..., Any], daily_ingestion)
