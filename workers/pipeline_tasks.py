import asyncio
import uuid
from collections.abc import Awaitable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update

from api.core.database import session_factory
from api.models import Job, PipelineRun
from api.services.recommendations import generate_daily_recommendations
from flows.daily_ingestion import run_alert_evaluation, run_daily_ingestion
from workers.async_runner import run_async
from workers.celery_app import app

PIPELINE_STALE_AFTER = timedelta(minutes=20)
INGESTION_TIMEOUT_SECONDS = 540
RECOMMENDATION_TIMEOUT_SECONDS = 120
ALERT_TIMEOUT_SECONDS = 120
MAINTENANCE_TIMEOUT_SECONDS = 30


def _pipeline_errors(result: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for stage in (
        "ingestion",
        "itviec",
        "topcv",
        "vietnamworks",
        "recommendations",
        "alerts",
        "maintenance",
    ):
        stage_result = result.get(stage)
        if not isinstance(stage_result, dict):
            continue
        before = len(errors)
        stage_errors = stage_result.get("errors")
        if isinstance(stage_errors, list):
            for error in stage_errors:
                errors.append({"stage": stage, "error": str(error)[:300]})
                if len(errors) >= 100:
                    return errors
        stage_status = stage_result.get("status")
        if stage_status in {"failed", "partial"} and len(errors) == before:
            errors.append({"stage": stage, "error": f"stage_status:{stage_status}"})
            if len(errors) >= 100:
                return errors
    return errors


async def _safe_stage(
    stage: str,
    operation: Awaitable[Mapping[str, object]],
    *,
    timeout_seconds: int,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = await asyncio.wait_for(operation, timeout=timeout_seconds)
        return dict(result)
    except Exception as exc:
        return {
            **fallback,
            "status": "failed",
            "errors": [f"{stage}:{type(exc).__name__}"],
        }


async def _expire_stale_jobs() -> dict[str, Any]:
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        expired_result = await session.execute(
            update(Job)
            .where(
                Job.is_active.is_(True),
                Job.posted_at < now - timedelta(days=60),
            )
            .values(is_active=False, updated_at=now)
        )
        expired = int(expired_result.rowcount or 0)  # type: ignore[attr-defined]
    return {"status": "completed", "expired_jobs": expired, "errors": []}


async def _execute_pipeline_stages() -> dict[str, Any]:
    """Run every daily stage in dependency order without cascading failures."""

    ingestion = await _safe_stage(
        "ingestion",
        run_daily_ingestion(evaluate_notifications=False),
        timeout_seconds=INGESTION_TIMEOUT_SECONDS,
        fallback={"jobs_found": 0},
    )
    recommendations = await _safe_stage(
        "recommendations",
        generate_daily_recommendations(),
        timeout_seconds=RECOMMENDATION_TIMEOUT_SECONDS,
        fallback={
            "users_considered": 0,
            "scores_created": 0,
            "recommendations_created": 0,
        },
    )
    alerts = await _safe_stage(
        "alerts",
        run_alert_evaluation(),
        timeout_seconds=ALERT_TIMEOUT_SECONDS,
        fallback={
            "alerts_checked": 0,
            "alerts_sent": 0,
            "deliveries_failed": 0,
        },
    )
    maintenance = await _safe_stage(
        "maintenance",
        _expire_stale_jobs(),
        timeout_seconds=MAINTENANCE_TIMEOUT_SECONDS,
        fallback={"expired_jobs": 0},
    )

    result = dict(ingestion)
    ingestion_status = str(ingestion.get("status", "failed"))
    result["ingestion"] = {
        "status": ingestion_status,
        "errors": ingestion.get("errors", []),
    }
    expired_jobs = maintenance.get("expired_jobs", 0)
    result["expired_jobs"] = expired_jobs if isinstance(expired_jobs, int) else 0
    result["recommendations"] = recommendations
    result["alerts"] = alerts
    result["maintenance"] = maintenance
    major_statuses = [
        ingestion_status,
        str(recommendations.get("status", "failed")),
        str(alerts.get("status", "failed")),
    ]
    all_statuses = [*major_statuses, str(maintenance.get("status", "failed"))]
    if all(stage == "completed" for stage in all_statuses):
        result["status"] = "completed"
    elif all(stage == "failed" for stage in major_statuses):
        result["status"] = "failed"
    else:
        result["status"] = "partial"
    return result


async def execute_daily_pipeline(
    run_id: uuid.UUID,
    *,
    reclaim_running: bool = False,
) -> dict[str, Any]:
    claimed_at = datetime.now(UTC)
    running_is_claimable = (
        PipelineRun.status == "running"
        if reclaim_running
        else and_(
            PipelineRun.status == "running",
            or_(
                PipelineRun.started_at.is_(None),
                PipelineRun.started_at < claimed_at - PIPELINE_STALE_AFTER,
            ),
        )
    )
    async with session_factory() as session, session.begin():
        claimed_id = await session.scalar(
            update(PipelineRun)
            .where(
                PipelineRun.id == run_id,
                PipelineRun.kind == "daily_ingestion",
                or_(
                    PipelineRun.status.in_(["queued", "failed"]),
                    running_is_claimable,
                ),
            )
            .values(
                status="running",
                started_at=claimed_at,
                completed_at=None,
                records_processed=0,
                errors=[],
                details={},
                updated_at=claimed_at,
            )
            .returning(PipelineRun.id)
        )
        if claimed_id is None:
            pipeline_run = await session.scalar(select(PipelineRun).where(PipelineRun.id == run_id))
            if pipeline_run is None:
                raise RuntimeError("Pipeline run does not exist")
            if pipeline_run.kind != "daily_ingestion":
                raise RuntimeError("Pipeline run kind does not match daily ingestion")
            return {**(pipeline_run.details or {}), "status": pipeline_run.status}

    try:
        result = await _execute_pipeline_stages()
        errors = _pipeline_errors(result)
        final_status = str(result["status"])
    except Exception as exc:
        result = {"status": "failed"}
        errors = [{"stage": "pipeline", "error": type(exc).__name__}]
        final_status = "failed"

    async with session_factory() as session, session.begin():
        finalized_id = await session.scalar(
            update(PipelineRun)
            .where(
                PipelineRun.id == run_id,
                PipelineRun.status == "running",
                PipelineRun.started_at == claimed_at,
            )
            .values(
                status=final_status,
                records_processed=(
                    int(result["jobs_found"]) if isinstance(result.get("jobs_found"), int) else 0
                ),
                errors=errors,
                details=result,
                completed_at=datetime.now(UTC),
            )
            .returning(PipelineRun.id)
        )
        if finalized_id is None:
            pipeline_run = await session.scalar(select(PipelineRun).where(PipelineRun.id == run_id))
            if pipeline_run is None:
                raise RuntimeError("Pipeline run disappeared before finalization")
            return {**(pipeline_run.details or {}), "status": pipeline_run.status}
    return result


@app.task(bind=True, name="workers.pipeline_tasks.run_daily_pipeline")
def run_daily_pipeline(task: Any, run_id: str) -> dict[str, Any]:
    delivery_info = getattr(task.request, "delivery_info", None)
    redelivered = isinstance(delivery_info, Mapping) and bool(delivery_info.get("redelivered"))
    return run_async(
        execute_daily_pipeline(
            uuid.UUID(run_id),
            reclaim_running=redelivered,
        )
    )
