from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.admin import require_admin_key
from api.core.database import get_session
from api.models import Job, RawJob, ScrapeBatch
from ml.salary.readiness import assess_salary_data_readiness
from ml.salary.training import load_salary_rows
from workers.ml_tasks import retrain_salary_model
from workers.scrape_tasks import scrape_itviec, scrape_vietnamworks

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_key)],
)
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/scrape/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape(
    platform: Literal["itviec", "vietnamworks"],
    pages: Annotated[int, Query(ge=1, le=50)] = 20,
    detail_limit: Annotated[int, Query(ge=0, le=100)] = 25,
) -> dict[str, str]:
    result = (
        scrape_itviec.delay(pages=pages, detail_limit=detail_limit)
        if platform == "itviec"
        else scrape_vietnamworks.delay(max_pages=min(pages, 10))
    )
    return {"status": "queued", "task_id": result.id, "platform": platform}


@router.post("/ml/retrain", status_code=status.HTTP_202_ACCEPTED)
async def trigger_retrain() -> dict[str, str]:
    result = retrain_salary_model.delay()
    return {"status": "queued", "task_id": result.id}


@router.get("/ml/data-readiness")
async def salary_data_readiness() -> dict[str, object]:
    return assess_salary_data_readiness(await load_salary_rows())


@router.get("/pipeline/status")
async def pipeline_status(session: Session) -> dict[str, object]:
    raw_count = await session.scalar(select(func.count()).select_from(RawJob)) or 0
    job_count = await session.scalar(select(func.count()).select_from(Job)) or 0
    latest = await session.scalar(
        select(ScrapeBatch).order_by(ScrapeBatch.started_at.desc()).limit(1)
    )
    return {
        "raw_jobs": raw_count,
        "normalized_jobs": job_count,
        "latest_batch": (
            {
                "id": str(latest.id),
                "platform": latest.platform,
                "status": latest.status,
                "started_at": latest.started_at,
                "completed_at": latest.completed_at,
            }
            if latest
            else None
        ),
    }


@router.get("/scrape/batches")
async def scrape_batches(
    session: Session, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> list[dict[str, object]]:
    batches = list(
        (
            await session.scalars(
                select(ScrapeBatch).order_by(ScrapeBatch.started_at.desc()).limit(limit)
            )
        ).all()
    )
    return [
        {
            "id": str(batch.id),
            "platform": batch.platform,
            "status": batch.status,
            "started_at": batch.started_at,
            "completed_at": batch.completed_at,
            "jobs_found": batch.jobs_found,
            "jobs_new": batch.jobs_new,
            "jobs_updated": batch.jobs_updated,
            "errors": batch.errors,
        }
        for batch in batches
    ]
