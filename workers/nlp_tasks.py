import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from api.core.database import session_factory
from api.models import Job, JobEmbedding, UserProfile
from api.services.profile_security import load_cv_text, set_profile_owner
from nlp.embeddings import MODEL_NAME, encode_texts
from workers.async_runner import run_async
from workers.celery_app import app


@app.task(name="workers.nlp_tasks.process_raw_job")
def process_raw_job(raw_job_id: str) -> dict[str, Any]:
    return {"status": "already_processed_during_ingestion", "raw_job_id": raw_job_id}


def _job_document(job: Job) -> str:
    skills = ", ".join([*job.skills_required, *job.skills_nice_to_have])
    return "\n".join(
        value
        for value in [job.title_normalized or job.title, skills, job.description_cleaned]
        if value
    )


async def _embed_jobs(limit: int) -> dict[str, Any]:
    async with session_factory() as session:
        jobs = list(
            (
                await session.scalars(
                    select(Job)
                    .outerjoin(JobEmbedding, JobEmbedding.job_id == Job.id)
                    .where(
                        Job.is_active.is_(True),
                        (JobEmbedding.job_id.is_(None)) | (JobEmbedding.model_name != MODEL_NAME),
                    )
                    .order_by(Job.posted_at.desc())
                    .limit(limit)
                )
            ).all()
        )
        vectors = encode_texts([_job_document(job) for job in jobs])
        for job, vector in zip(jobs, vectors, strict=True):
            statement = insert(JobEmbedding).values(
                job_id=job.id, embedding=vector, model_name=MODEL_NAME
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[JobEmbedding.job_id],
                    set_={"embedding": vector, "model_name": MODEL_NAME},
                )
            )
        await session.commit()
    return {"status": "completed", "embedded": len(jobs), "model": MODEL_NAME}


@app.task(name="workers.nlp_tasks.embed_jobs")
def embed_jobs(limit: int = 500) -> dict[str, Any]:
    if not 1 <= limit <= 2_000:
        raise ValueError("limit must be between 1 and 2000")
    try:
        return run_async(_embed_jobs(limit))
    except ModuleNotFoundError as exc:
        return {"status": "skipped", "reason": "ml_extra_not_installed", "missing": exc.name}


async def _embed_profile(user_id: uuid.UUID) -> dict[str, Any]:
    async with session_factory() as session:
        await set_profile_owner(session, user_id)
        profile = await session.get(UserProfile, user_id)
        if profile is None or not profile.has_cv:
            return {"status": "skipped", "reason": "profile_or_cv_not_found"}
        cv_text = await load_cv_text(session, user_id)
        if not cv_text:
            return {"status": "skipped", "reason": "profile_or_cv_not_found"}
        profile.cv_embedding = encode_texts([cv_text])[0]
        await session.commit()
    return {"status": "completed", "user_id": str(user_id), "model": MODEL_NAME}


@app.task(name="workers.nlp_tasks.embed_profile")
def embed_profile(user_id: str) -> dict[str, Any]:
    try:
        parsed_id = uuid.UUID(user_id)
    except ValueError:
        return {"status": "rejected", "reason": "invalid_user_id"}
    try:
        return run_async(_embed_profile(parsed_id))
    except ModuleNotFoundError as exc:
        return {"status": "skipped", "reason": "ml_extra_not_installed", "missing": exc.name}
