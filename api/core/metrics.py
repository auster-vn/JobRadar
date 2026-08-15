import asyncio
import json
import logging
import math
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from redis.asyncio import Redis
from sqlalchemy import func, select

from api.core.config import get_settings
from api.core.database import session_factory
from api.models import Job, JobAlert, ScrapeBatch

logger = logging.getLogger(__name__)

REQUESTS = Counter("jobradar_http_requests_total", "API requests", ("method", "path", "status"))
LATENCY = Histogram("jobradar_http_request_duration_seconds", "API latency", ("method", "path"))
JOBS = Gauge("jobradar_jobs_total", "Indexed normalized jobs")
ACTIVE_ALERTS = Gauge("jobradar_active_alerts_total", "Active job alerts")
LAST_SCRAPE_AGE = Gauge(
    "jobradar_last_successful_scrape_age_seconds",
    "Age of the latest successful scrape batch",
    ("platform",),
)
QUEUE_LENGTH = Gauge("jobradar_celery_queue_length", "Celery queue backlog", ("queue",))
DEPENDENCY_AVAILABLE = Gauge(
    "jobradar_dependency_available",
    "Whether an external dependency was reachable during metrics collection",
    ("dependency",),
)
SALARY_MODEL_MAPE = Gauge("jobradar_salary_model_mape", "Latest salary model MAPE")
SALARY_MODEL_INTERVAL_COVERAGE = Gauge(
    "jobradar_salary_model_interval_coverage",
    "Latest salary model P25 to P75 interval coverage",
)
SALARY_MODEL_PUBLISHED = Gauge(
    "jobradar_salary_model_published",
    "Latest salary model evaluation publication status",
)
SALARY_DATA_READY = Gauge("jobradar_salary_data_ready", "Salary training data readiness status")
SALARY_DATA_DISTINCT_MONTHS = Gauge(
    "jobradar_salary_data_distinct_months", "Distinct monthly salary observation periods"
)
SALARY_DATA_CANONICAL_ROWS = Gauge(
    "jobradar_salary_data_canonical_rows", "Salary rows mapped to canonical technical roles"
)
SALARY_DATA_FINAL_MONTH_ROWS = Gauge(
    "jobradar_salary_data_final_month_rows", "Salary rows in the latest observation month"
)
SALARY_MODEL_MAPE.set(-1)
SALARY_MODEL_INTERVAL_COVERAGE.set(-1)
SALARY_MODEL_PUBLISHED.set(-1)
SALARY_DATA_READY.set(-1)
SALARY_DATA_DISTINCT_MONTHS.set(-1)
SALARY_DATA_CANONICAL_ROWS.set(-1)
SALARY_DATA_FINAL_MONTH_ROWS.set(-1)


def set_salary_evaluation_metrics(evaluation: dict[str, object]) -> None:
    test_mape = evaluation.get("test_mape")
    if isinstance(test_mape, int | float):
        SALARY_MODEL_MAPE.set(test_mape)
    interval_coverage = evaluation.get("interval_coverage")
    if isinstance(interval_coverage, int | float):
        SALARY_MODEL_INTERVAL_COVERAGE.set(interval_coverage)
    SALARY_MODEL_PUBLISHED.set(float(evaluation.get("status") == "published"))
    readiness = evaluation.get("data_readiness")
    if not isinstance(readiness, dict):
        return
    SALARY_DATA_READY.set(float(readiness.get("ready") is True))
    distinct_months = readiness.get("distinct_months")
    if isinstance(distinct_months, int | float):
        SALARY_DATA_DISTINCT_MONTHS.set(distinct_months)
    canonical_rows = readiness.get("canonical_technical_rows")
    if isinstance(canonical_rows, int | float):
        SALARY_DATA_CANONICAL_ROWS.set(canonical_rows)
    final_month_rows = readiness.get("final_month_rows")
    if isinstance(final_month_rows, int | float):
        SALARY_DATA_FINAL_MONTH_ROWS.set(final_month_rows)


def _scrape_ages(
    completed_at: dict[str, datetime],
    enabled_platforms: set[str],
    *,
    now: datetime,
) -> dict[str, float]:
    ages: dict[str, float] = {}
    for platform in enabled_platforms:
        completed = completed_at.get(platform)
        ages[platform] = (
            math.inf if completed is None else max(0, (now - completed).total_seconds())
        )
    return ages


async def metrics_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    REQUESTS.labels(request.method, path, response.status_code).inc()
    LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
    return response


async def metrics_response() -> Response:
    settings = get_settings()
    enabled_platforms = {
        platform
        for platform, enabled in (
            ("itviec", settings.enable_itviec_scraper),
            ("topcv", settings.enable_topcv_scraper),
            ("vietnamworks", settings.enable_vietnamworks_scraper),
        )
        if enabled
    }
    try:
        async with asyncio.timeout(3), session_factory() as session:
            JOBS.set(await session.scalar(select(func.count()).select_from(Job)) or 0)
            ACTIVE_ALERTS.set(
                await session.scalar(
                    select(func.count()).select_from(JobAlert).where(JobAlert.is_active.is_(True))
                )
                or 0
            )
            completed_at: dict[str, datetime] = {}
            if enabled_platforms:
                rows = await session.execute(
                    select(ScrapeBatch.platform, func.max(ScrapeBatch.completed_at))
                    .where(
                        ScrapeBatch.status == "completed",
                        ScrapeBatch.platform.in_(enabled_platforms),
                    )
                    .group_by(ScrapeBatch.platform)
                )
                completed_at = {
                    platform: completed for platform, completed in rows if completed is not None
                }
            for platform, age in _scrape_ages(
                completed_at, enabled_platforms, now=datetime.now(UTC)
            ).items():
                LAST_SCRAPE_AGE.labels(platform).set(age)
        DEPENDENCY_AVAILABLE.labels("database").set(1)
    except Exception as exc:
        DEPENDENCY_AVAILABLE.labels("database").set(0)
        logger.warning("Could not collect database metrics: %s", exc)

    redis: Redis | None = None
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        async with asyncio.timeout(3):
            for queue in ("alerts", "nlp", "scraping", "ml", "analytics"):
                length = await cast(Awaitable[int], redis.llen(queue))
                QUEUE_LENGTH.labels(queue).set(length)
            raw_evaluation = await redis.get("model:salary:latest_evaluation")
            if raw_evaluation:
                evaluation = json.loads(raw_evaluation)
                if isinstance(evaluation, dict):
                    set_salary_evaluation_metrics(evaluation)
        DEPENDENCY_AVAILABLE.labels("cache").set(1)
    except Exception as exc:
        DEPENDENCY_AVAILABLE.labels("cache").set(0)
        logger.warning("Could not collect Redis queue metrics: %s", exc)
    finally:
        if redis is not None:
            await redis.aclose()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
