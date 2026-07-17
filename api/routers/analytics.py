from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_session
from api.schemas.jobs import SkillDemand

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/skills/demand", response_model=list[SkillDemand])
async def skill_demand(
    session: Session, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[SkillDemand]:
    rows = await session.execute(
        text(
            """
            WITH monthly AS (
              SELECT skill, date_trunc('month', posted_at) AS month, count(*) AS job_count
              FROM jobs, unnest(skills_required) AS skill
              WHERE is_active = true AND posted_at >= now() - interval '3 months'
              GROUP BY skill, date_trunc('month', posted_at)
            ), totals AS (
              SELECT skill, sum(job_count)::int AS total,
                sum(job_count) FILTER (WHERE month = date_trunc('month', now())) AS current_count,
                sum(job_count) FILTER (
                  WHERE month = date_trunc('month', now()) - interval '1 month'
                ) AS previous_count
              FROM monthly GROUP BY skill
            )
            SELECT skill, total AS job_count,
              row_number() OVER (ORDER BY total DESC)::int AS demand_rank,
              round(
                (current_count - previous_count)::numeric
                / nullif(previous_count, 0) * 100, 1
              )::float AS mom_growth_pct
            FROM totals ORDER BY total DESC LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [SkillDemand.model_validate(dict(row)) for row in rows.mappings()]


@router.get("/market/overview")
async def market_overview(session: Session) -> dict[str, object]:
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT count(*) FILTER (WHERE is_active) AS active_jobs,
                  count(DISTINCT company_id) FILTER (WHERE is_active) AS companies,
                  count(*) FILTER (
                    WHERE is_active AND posted_at >= now() - interval '7 days'
                  ) AS new_this_week,
                  round(avg((salary_min + salary_max) / 2) FILTER (
                    WHERE is_active AND salary_min IS NOT NULL AND salary_max IS NOT NULL
                  ))::bigint AS average_salary
                FROM jobs
                """
                )
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


@router.get("/skills/trending")
async def trending_skills(
    session: Session, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict[str, object]]:
    rows = await session.execute(
        text(
            """
            WITH counts AS (
              SELECT skill,
                count(*) FILTER (
                  WHERE posted_at >= now() - interval '30 days'
                )::int AS current_jobs,
                count(*) FILTER (
                  WHERE posted_at >= now() - interval '60 days'
                    AND posted_at < now() - interval '30 days'
                )::int AS previous_jobs
              FROM jobs, unnest(skills_required) skill
              WHERE is_active AND posted_at >= now() - interval '60 days'
              GROUP BY skill
            )
            SELECT skill, current_jobs, previous_jobs,
              round(
                (current_jobs - previous_jobs)::numeric
                / nullif(previous_jobs, 0) * 100, 1
              )::float AS growth_pct
            FROM counts WHERE current_jobs > 0
            ORDER BY growth_pct DESC NULLS LAST, current_jobs DESC LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [dict(row) for row in rows.mappings()]


@router.get("/hiring/trends")
async def hiring_trends(
    session: Session, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict[str, object]]:
    rows = await session.execute(
        text(
            """
            SELECT c.id AS company_id, c.name AS company,
              count(*) FILTER (
                WHERE j.posted_at >= now() - interval '30 days'
              )::int AS current_jobs,
              count(*) FILTER (
                WHERE j.posted_at >= now() - interval '60 days'
                  AND j.posted_at < now() - interval '30 days'
              )::int AS previous_jobs
            FROM jobs j JOIN companies c ON c.id = j.company_id
            WHERE j.is_active AND j.posted_at >= now() - interval '60 days'
            GROUP BY c.id, c.name
            ORDER BY current_jobs DESC, company LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [dict(row) for row in rows.mappings()]


async def _salary_breakdown(session: AsyncSession, dimension: str) -> list[dict[str, object]]:
    expression = "skill" if dimension == "skill" else "coalesce(c.company_type, 'unknown')"
    join = ", unnest(j.skills_required) skill" if dimension == "skill" else ""
    rows = await session.execute(
        text(
            f"""
            SELECT {expression} AS segment, count(*)::int AS sample_size,
              percentile_cont(0.5) WITHIN GROUP (
                ORDER BY coalesce(
                  (j.salary_min + j.salary_max) / 2, j.salary_min, j.salary_max
                )
              )::bigint AS median_salary
            FROM jobs j JOIN companies c ON c.id = j.company_id {join}
            WHERE j.is_active AND (j.salary_min IS NOT NULL OR j.salary_max IS NOT NULL)
              AND j.posted_at >= now() - interval '6 months'
            GROUP BY {expression} HAVING count(*) >= 3
            ORDER BY median_salary DESC LIMIT 100
            """  # noqa: S608 -- dimension selects from two internal constants only.
        )
    )
    return [dict(row) for row in rows.mappings()]


@router.get("/salary/by-skill")
async def salary_by_skill(session: Session) -> list[dict[str, object]]:
    return await _salary_breakdown(session, "skill")


@router.get("/salary/by-company-type")
async def salary_by_company_type(session: Session) -> list[dict[str, object]]:
    return await _salary_breakdown(session, "company_type")
