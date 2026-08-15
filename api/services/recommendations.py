import uuid
from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import func, select, text

from api.core.config import get_settings
from api.core.database import session_factory
from api.models import Job, Notification, User, UserProfile
from api.services.profile_security import set_profile_owner
from api.services.scoring import (
    DeterministicScoringProvider,
    ScoreComputation,
    build_score_inputs,
    compute_deterministic_score,
    get_or_create_job_score,
)


class RecommendationResult(TypedDict):
    status: str
    users_considered: int
    scores_created: int
    recommendations_created: int
    errors: list[str]


def _rank_jobs(
    jobs: list[Job],
    profile: UserProfile,
    *,
    minimum_score: int,
    limit: int,
) -> list[tuple[ScoreComputation, Job]]:
    ranked = [(compute_deterministic_score(build_score_inputs(job, profile)), job) for job in jobs]
    ranked = [item for item in ranked if item[0].overall_score >= minimum_score]
    ranked.sort(
        key=lambda item: (
            item[0].overall_score,
            item[1].posted_at or datetime.min.replace(tzinfo=UTC),
            str(item[1].id),
        ),
        reverse=True,
    )
    return ranked[:limit]


async def generate_daily_recommendations() -> RecommendationResult:
    """Build a bounded, no-LLM recommendation set for active candidates."""

    settings = get_settings()
    async with session_factory() as session:
        jobs = list(
            (
                await session.scalars(
                    select(Job)
                    .where(
                        Job.is_active.is_(True),
                        Job.posted_at >= func.now() - text("interval '7 days'"),
                    )
                    .order_by(Job.posted_at.desc(), Job.id.desc())
                    .limit(settings.daily_recommendation_job_limit)
                )
            ).all()
        )
        user_ids = list(
            (
                await session.scalars(
                    select(User.id)
                    .where(User.is_active.is_(True))
                    .order_by(User.id)
                    .limit(settings.daily_recommendation_user_limit)
                )
            ).all()
        )

    scores_created = 0
    recommendations_created = 0
    errors: list[str] = []
    provider = DeterministicScoringProvider()
    for user_id in user_ids:
        if len(errors) >= 100:
            break
        try:
            async with session_factory() as session:
                await set_profile_owner(session, user_id)
                profile = await session.scalar(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                )
                if profile is None or not profile.skills:
                    continue
                ranked = _rank_jobs(
                    jobs,
                    profile,
                    minimum_score=settings.daily_recommendation_min_score,
                    limit=settings.daily_recommendations_per_user,
                )
                for computation, job in ranked:
                    if len(errors) >= 100:
                        break
                    try:
                        _, cached = await get_or_create_job_score(
                            session,
                            user_id=user_id,
                            job=job,
                            profile=profile,
                            provider=provider,
                        )
                        scores_created += int(not cached)
                        await set_profile_owner(session, user_id)
                        await session.execute(
                            text(
                                """
                                SELECT pg_advisory_xact_lock(
                                  hashtextextended(cast(:key as text), 0)
                                )
                                """
                            ),
                            {"key": f"job-recommendation:{user_id}:{job.id}"},
                        )
                        existing = await session.scalar(
                            select(Notification.id).where(
                                Notification.user_id == user_id,
                                Notification.job_id == job.id,
                                Notification.kind == "job_recommendation",
                            )
                        )
                        if existing is not None:
                            await session.commit()
                            continue
                        session.add(
                            Notification(
                                id=uuid.uuid4(),
                                user_id=user_id,
                                job_id=job.id,
                                kind="job_recommendation",
                                channel="in_app",
                                status="pending",
                                title=f"{job.title} is a strong match",
                                body=(
                                    f"Your deterministic JobRadar fit score is "
                                    f"{computation.overall_score:.0f}/100."
                                ),
                                payload={
                                    "job_id": str(job.id),
                                    "score": str(computation.overall_score),
                                },
                            )
                        )
                        await session.commit()
                        recommendations_created += 1
                    except Exception as exc:
                        await session.rollback()
                        errors.append(f"{user_id}:{job.id}:{type(exc).__name__}")
        except Exception as exc:
            errors.append(f"{user_id}:user:{type(exc).__name__}")
    return {
        "status": "partial" if errors else "completed",
        "users_considered": len(user_ids),
        "scores_created": scores_created,
        "recommendations_created": recommendations_created,
        "errors": errors,
    }
