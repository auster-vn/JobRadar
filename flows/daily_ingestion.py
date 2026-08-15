import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from workers.alert_tasks import (
    ALERT_EVALUATION_TIMEOUT_SECONDS,
    bounded_alert_evaluation,
    evaluate_alerts,
)
from workers.scrape_tasks import ScrapeResult, ingest_itviec, ingest_topcv, ingest_vietnamworks

MAX_DAILY_ITVIEC_PAGES = 20
SOURCE_TIMEOUT_SECONDS = 480


async def _safe_source(source: str, operation: Awaitable[ScrapeResult]) -> ScrapeResult:
    try:
        return await asyncio.wait_for(operation, timeout=SOURCE_TIMEOUT_SECONDS)
    except Exception as exc:
        return {
            "source": source,
            "status": "failed",
            "jobs_found": 0,
            "errors": [f"source:{type(exc).__name__}"],
            "jobs_new": 0,
            "jobs_updated": 0,
        }


async def run_alert_evaluation() -> dict[str, Any]:
    return await bounded_alert_evaluation(
        evaluate_alerts(),
        timeout_seconds=ALERT_EVALUATION_TIMEOUT_SECONDS,
    )


async def run_daily_ingestion(
    pages: int = 20,
    *,
    evaluate_notifications: bool = True,
) -> dict[str, Any]:
    bounded_pages = max(1, min(pages, MAX_DAILY_ITVIEC_PAGES))
    itviec, topcv, vietnamworks = await asyncio.gather(
        _safe_source("itviec", ingest_itviec(bounded_pages)),
        _safe_source("topcv", ingest_topcv()),
        _safe_source("vietnamworks", ingest_vietnamworks()),
    )
    alerts = (
        await run_alert_evaluation()
        if evaluate_notifications
        else {"status": "deferred", "errors": []}
    )
    sources = [itviec, topcv, vietnamworks]
    failures = sum(result["status"] in {"failed", "partial"} for result in sources)
    return {
        "status": (
            "completed"
            if failures == 0 and alerts["status"] in {"completed", "deferred"}
            else "partial"
        ),
        "jobs_found": sum(result["jobs_found"] for result in sources),
        "itviec": itviec,
        "topcv": topcv,
        "vietnamworks": vietnamworks,
        "alerts": alerts,
    }


def prefect_flow() -> Callable[..., Any]:
    """Build the Prefect flow only when the orchestration extra is installed."""
    from prefect import flow

    @flow(name="jobradar-daily-ingestion", log_prints=True)
    def daily_ingestion(pages: int = 20) -> dict[str, Any]:
        return asyncio.run(run_daily_ingestion(pages))

    return cast(Callable[..., Any], daily_ingestion)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_daily_ingestion()), default=str))
