import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, Text, and_, cast, func, or_, select, text, tuple_
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.config import get_settings
from api.core.database import get_session
from api.core.pagination import decode_cursor, encode_cursor
from api.models import Job, JobEmbedding
from api.schemas.jobs import JobDetail, JobPage, JobSummary, Pagination

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=JobPage)
async def list_jobs(
    session: Session,
    query: Annotated[str | None, Query(max_length=200)] = None,
    level: str | None = None,
    location: str | None = None,
    skill: str | None = None,
    remote: bool | None = None,
    salary_min: Annotated[int | None, Query(ge=0)] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1)] = 20,
) -> JobPage:
    limit = min(limit, get_settings().max_jobs_per_page)
    filters: list[ColumnElement[bool]] = [Job.is_active.is_(True)]
    if query:
        needle = f"%{query.strip()}%"
        filters.append(or_(Job.title.ilike(needle), Job.description_cleaned.ilike(needle)))
    if level:
        filters.append(Job.job_level == level)
    if location:
        filters.append(Job.location.contains([location]))
    if skill:
        filters.append(Job.skills_required.contains([skill]))
    if remote is True:
        filters.append(or_(Job.job_type == "remote", Job.location.contains(["Remote"])))
    if salary_min is not None:
        filters.append(Job.salary_max >= salary_min)
    count_filters = list(filters)
    if cursor:
        parsed = decode_cursor(cursor)
        filters.append(tuple_(Job.posted_at, Job.id) < (parsed.posted_at, parsed.job_id))

    statement = (
        select(Job)
        .where(and_(*filters))
        .options(selectinload(Job.company))
        .order_by(Job.posted_at.desc(), Job.id.desc())
        .limit(limit + 1)
    )
    jobs = list((await session.scalars(statement)).all())
    has_more = len(jobs) > limit
    page_items = jobs[:limit]
    next_cursor = None
    if has_more and page_items and page_items[-1].posted_at:
        next_cursor = encode_cursor(page_items[-1].posted_at, page_items[-1].id)

    total = await session.scalar(select(func.count(Job.id)).where(and_(*count_filters)))
    return JobPage(
        data=[JobSummary.model_validate(job) for job in page_items],
        pagination=Pagination(
            limit=limit,
            next_cursor=next_cursor,
            has_more=has_more,
            total_count=total or 0,
        ),
    )


@router.get("/trending", response_model=list[JobSummary])
async def trending_jobs(
    session: Session, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> list[JobSummary]:
    jobs = list(
        (
            await session.scalars(
                select(Job)
                .where(
                    Job.is_active.is_(True),
                    Job.posted_at >= func.now() - text("interval '7 days'"),
                )
                .options(selectinload(Job.company))
                .order_by(Job.posted_at.desc())
                .limit(limit)
            )
        ).all()
    )
    return [JobSummary.model_validate(job) for job in jobs]


@router.get("/{job_id}/similar", response_model=list[JobSummary])
async def similar_jobs(
    job_id: uuid.UUID,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[JobSummary]:
    source_job = await session.scalar(select(Job).where(Job.id == job_id))
    if source_job is None or not source_job.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    source_embedding = await session.get(JobEmbedding, job_id)
    if source_embedding is not None:
        distance = JobEmbedding.embedding.cosine_distance(source_embedding.embedding)
        statement = (
            select(Job)
            .join(JobEmbedding, JobEmbedding.job_id == Job.id)
            .where(Job.id != job_id, Job.is_active.is_(True))
            .order_by(distance)
        )
    else:
        title_match = Job.title_normalized == source_job.title_normalized
        fallback_filters: list[ColumnElement[bool]] = [title_match]
        if source_job.skills_required:
            fallback_filters.append(
                Job.skills_required.op("&&")(cast(source_job.skills_required, ARRAY(Text)))
            )
        statement = (
            select(Job)
            .where(
                Job.id != job_id,
                Job.is_active.is_(True),
                or_(*fallback_filters),
            )
            .order_by(title_match.desc(), Job.posted_at.desc())
        )
    jobs = list(
        (await session.scalars(statement.options(selectinload(Job.company)).limit(limit))).all()
    )
    return [JobSummary.model_validate(job) for job in jobs]


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: uuid.UUID, session: Session) -> JobDetail:
    job = await session.scalar(
        select(Job).where(Job.id == job_id).options(selectinload(Job.company))
    )
    if not job or not job.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return JobDetail.model_validate(job)
