import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.cron import require_cron_secret
from api.core.database import get_session
from api.models import PipelineRun
from workers.pipeline_tasks import PIPELINE_STALE_AFTER, run_daily_pipeline

router = APIRouter(
    prefix="/api/cron",
    tags=["automation"],
    dependencies=[Depends(require_cron_secret)],
)
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/daily", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_daily_pipeline(
    session: Session,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ] = None,
) -> dict[str, str]:
    now = datetime.now(UTC)
    key = (idempotency_key or f"daily:{now.date().isoformat()}").strip()
    if not 8 <= len(key) <= 128:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Idempotency-Key must contain 8 to 128 non-whitespace characters",
        )
    run_id = uuid.uuid4()
    created_id = await session.scalar(
        insert(PipelineRun)
        .values(
            id=run_id,
            kind="daily_ingestion",
            status="queued",
            idempotency_key=key,
        )
        .on_conflict_do_nothing(constraint="uq_pipeline_runs_idempotency_key")
        .returning(PipelineRun.id)
    )
    if created_id is None:
        existing = await session.scalar(
            select(PipelineRun).where(PipelineRun.idempotency_key == key)
        )
        if existing is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A pipeline run already uses this idempotency key",
            )
        if existing.kind != "daily_ingestion":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Idempotency-Key belongs to a different pipeline kind",
            )
        run_id = existing.id
        stale_running = existing.status == "running" and (
            existing.started_at is None or existing.started_at < now - PIPELINE_STALE_AFTER
        )
        if existing.status == "failed" or stale_running:
            retry_id = await session.scalar(
                update(PipelineRun)
                .where(
                    PipelineRun.id == run_id,
                    or_(
                        PipelineRun.status == "failed",
                        and_(
                            PipelineRun.status == "running",
                            or_(
                                PipelineRun.started_at.is_(None),
                                PipelineRun.started_at < now - PIPELINE_STALE_AFTER,
                            ),
                        ),
                    ),
                )
                .values(
                    status="queued",
                    records_processed=0,
                    errors=[],
                    details={},
                    started_at=None,
                    completed_at=None,
                    updated_at=now,
                )
                .returning(PipelineRun.id)
            )
            if retry_id is None:
                await session.rollback()
                current = await session.scalar(select(PipelineRun).where(PipelineRun.id == run_id))
                if current is None:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        "Pipeline run changed during retry",
                    )
                return {
                    "status": current.status,
                    "run_id": str(current.id),
                    "idempotency_key": key,
                }
        elif existing.status != "queued":
            return {
                "status": existing.status,
                "run_id": str(existing.id),
                "idempotency_key": key,
            }

    await session.commit()
    try:
        task = run_daily_pipeline.delay(str(run_id))
    except Exception as exc:
        await session.execute(
            update(PipelineRun)
            .where(
                PipelineRun.id == run_id,
                PipelineRun.status == "queued",
            )
            .values(
                status="failed",
                completed_at=datetime.now(UTC),
                errors=[{"stage": "enqueue", "error": type(exc).__name__}],
            )
        )
        await session.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Background queue is temporarily unavailable",
        ) from exc
    return {
        "status": "queued",
        "run_id": str(run_id),
        "task_id": task.id,
        "idempotency_key": key,
    }
