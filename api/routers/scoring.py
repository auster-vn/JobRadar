import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_session
from api.core.security import get_current_user
from api.models import Job, User, UserProfile
from api.schemas.scoring import JobScoreResponse
from api.services.profile_security import set_profile_owner
from api.services.scoring import (
    ScoringBudgetExceeded,
    ScoringBudgetUnavailable,
    get_or_create_job_score,
)

router = APIRouter(prefix="/api/jobs", tags=["scoring"])
Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/{job_id}/score",
    response_model=JobScoreResponse,
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Daily AI scoring budget exhausted"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Production AI budget enforcement unavailable"
        },
    },
)
async def score_job(
    job_id: uuid.UUID,
    response: Response,
    user: CurrentUser,
    session: Session,
) -> JobScoreResponse:
    job = await session.scalar(select(Job).where(Job.id == job_id, Job.is_active.is_(True)))
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    await set_profile_owner(session, user.id)
    profile = await session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        profile = UserProfile(
            user_id=user.id,
            skills=[],
            preferred_locations=[],
            preferred_job_types=[],
        )
    try:
        score, cached = await get_or_create_job_score(
            session,
            user_id=user.id,
            job=job,
            profile=profile,
        )
    except ScoringBudgetExceeded as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ScoringBudgetUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI scoring budget enforcement is unavailable",
        ) from exc
    response.headers["Cache-Control"] = "private, no-store"
    return JobScoreResponse.model_validate(score).model_copy(update={"cached": cached})
