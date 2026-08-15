import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.database import get_session
from api.core.security import get_current_user
from api.models import Job, User, UserProfile
from api.schemas.jobs import JobSummary
from api.schemas.profile import MatchedJob, ProfileResponse, ProfileUpdate, SkillGapResponse
from api.services.cv_service import MAX_CV_BYTES, extract_cv
from api.services.profile_security import set_profile_owner, store_cv_text
from api.services.storage import (
    StorageUnavailable,
    storage_enabled,
)
from api.services.storage import (
    delete_cv as delete_stored_cv,
)
from api.services.storage import (
    upload_cv as upload_stored_cv,
)
from nlp.skill_extractor import extract_skills
from workers.nlp_tasks import embed_profile

router = APIRouter(prefix="/api/profile", tags=["profile"])
Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
logger = logging.getLogger(__name__)


async def _profile(session: AsyncSession, user_id: uuid.UUID) -> UserProfile:
    await set_profile_owner(session, user_id)
    profile = await session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        profile = UserProfile(user_id=user_id)
        session.add(profile)
        await session.flush()
    return profile


@router.get("", response_model=ProfileResponse)
async def get_profile(user: CurrentUser, session: Session) -> ProfileResponse:
    return ProfileResponse.model_validate(await _profile(session, user.id))


@router.put("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdate, user: CurrentUser, session: Session
) -> ProfileResponse:
    profile = await _profile(session, user.id)
    for field, value in payload.model_dump().items():
        setattr(profile, field, value)
    await session.commit()
    await session.refresh(profile)
    return ProfileResponse.model_validate(profile)


@router.post("/cv", response_model=ProfileResponse)
async def upload_cv(
    user: CurrentUser,
    session: Session,
    file: Annotated[UploadFile, File(description="PDF, DOCX or UTF-8 text; maximum 5 MB")],
) -> ProfileResponse:
    data = await file.read(MAX_CV_BYTES + 1)
    cv_text = await extract_cv(file.filename, data)
    extracted = extract_skills(cv_text)
    profile = await _profile(session, user.id)
    previous_storage_path = profile.cv_storage_path
    new_storage_path: str | None = None
    if storage_enabled():
        try:
            new_storage_path = await upload_stored_cv(
                user.id,
                file.filename,
                data,
                file.content_type,
            )
        except StorageUnavailable as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Candidate file storage is temporarily unavailable",
            ) from exc
    await store_cv_text(session, user.id, cv_text)
    profile.skills = sorted({*profile.skills, *extracted.required, *extracted.nice_to_have})
    if new_storage_path:
        profile.cv_storage_path = new_storage_path
    try:
        await session.commit()
    except Exception:
        if new_storage_path and new_storage_path != previous_storage_path:
            try:
                await delete_stored_cv(new_storage_path)
            except StorageUnavailable:
                logger.warning("Could not clean up unreferenced CV object")
        raise
    await session.refresh(profile)
    if (
        new_storage_path is not None
        and previous_storage_path
        and previous_storage_path != new_storage_path
    ):
        try:
            await delete_stored_cv(previous_storage_path)
        except StorageUnavailable:
            logger.warning("Could not remove superseded CV object")
    try:
        embed_profile.delay(str(user.id))
    except Exception:
        logger.warning("Could not enqueue CV embedding", exc_info=True)
    return ProfileResponse.model_validate(profile)


@router.delete("/cv", response_model=ProfileResponse)
async def delete_cv(user: CurrentUser, session: Session) -> ProfileResponse:
    profile = await _profile(session, user.id)
    storage_path = profile.cv_storage_path
    profile.cv_text_encrypted = None
    profile.cv_embedding = None
    profile.cv_storage_path = None
    await session.commit()
    await session.refresh(profile)
    try:
        await delete_stored_cv(storage_path)
    except StorageUnavailable:
        logger.warning("Could not remove CV object after profile deletion")
    return ProfileResponse.model_validate(profile)


@router.get("/matching-jobs", response_model=list[MatchedJob])
async def matching_jobs(
    user: CurrentUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    min_skill_match_pct: Annotated[float, Query(ge=0, le=100)] = 30,
) -> list[MatchedJob]:
    profile = await _profile(session, user.id)
    user_skills = {skill.casefold(): skill for skill in profile.skills}
    semantic_enabled = profile.cv_embedding is not None
    rows: list[tuple[Job, float | None]]
    if semantic_enabled:
        from api.models import JobEmbedding

        distance = JobEmbedding.embedding.cosine_distance(profile.cv_embedding).label("distance")
        result_rows = (
            await session.execute(
                select(Job, distance)
                .join(JobEmbedding, JobEmbedding.job_id == Job.id)
                .where(Job.is_active.is_(True))
                .options(selectinload(Job.company))
                .order_by(distance, Job.posted_at.desc())
                .limit(250)
            )
        ).all()
        rows = [(row[0], float(row[1])) for row in result_rows]
    else:
        jobs = list(
            (
                await session.scalars(
                    select(Job)
                    .where(Job.is_active.is_(True))
                    .options(selectinload(Job.company))
                    .order_by(Job.posted_at.desc())
                    .limit(250)
                )
            ).all()
        )
        rows = [(job, None) for job in jobs]
    ranked: list[tuple[float, float, float | None, list[str], Job]] = []
    for job, semantic_distance in rows:
        required = {skill.casefold(): skill for skill in job.skills_required}
        matched_keys = set(required) & set(user_skills)
        skill_score = len(matched_keys) / max(1, len(required)) * 100
        semantic_score = (
            max(0.0, min(100.0, (1 - float(semantic_distance)) * 100))
            if semantic_distance is not None
            else None
        )
        match_score = (
            skill_score * 0.7 + semantic_score * 0.3 if semantic_score is not None else skill_score
        )
        if skill_score >= min_skill_match_pct:
            ranked.append(
                (
                    match_score,
                    skill_score,
                    semantic_score,
                    sorted(required[key] for key in matched_keys),
                    job,
                )
            )
    ranked.sort(key=lambda item: (item[0], item[4].posted_at), reverse=True)
    return [
        MatchedJob(
            job=JobSummary.model_validate(job),
            skill_match_pct=round(skill_score, 1),
            semantic_match_pct=round(semantic_score, 1) if semantic_score is not None else None,
            match_score=round(match_score, 1),
            matched_skills=matched,
        )
        for match_score, skill_score, semantic_score, matched, job in ranked[:limit]
    ]


@router.get("/skill-gap", response_model=SkillGapResponse)
async def skill_gap(
    target_title: Annotated[str, Query(min_length=2, max_length=200)],
    target_level: str,
    user: CurrentUser,
    session: Session,
) -> SkillGapResponse:
    profile = await _profile(session, user.id)
    rows = await session.execute(
        text(
            """
            SELECT skill, count(*) AS demand
            FROM jobs, unnest(skills_required) AS skill
            WHERE is_active = true
              AND title_normalized ILIKE '%' || cast(:title as text) || '%'
              AND job_level = cast(:level as text)
            GROUP BY skill ORDER BY demand DESC LIMIT 15
            """
        ),
        {"title": target_title, "level": target_level},
    )
    target_skills = [row.skill for row in rows]
    current_lookup = {item.casefold() for item in profile.skills}
    missing = [item for item in target_skills if item.casefold() not in current_lookup]
    coverage = (len(target_skills) - len(missing)) / max(1, len(target_skills)) * 100
    return SkillGapResponse(
        target_title=target_title,
        target_level=target_level,
        current_skills=profile.skills,
        missing_skills=missing,
        coverage_pct=round(coverage, 1),
    )
