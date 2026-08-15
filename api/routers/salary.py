from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_session
from api.schemas.jobs import SalaryBand
from api.schemas.salary import SalaryPredictionRequest, SalaryPredictionResponse
from api.services.salary_model import request_published_salary_model

router = APIRouter(prefix="/api/salary", tags=["salary"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/predict", response_model=SalaryPredictionResponse)
async def predict_salary(
    payload: SalaryPredictionRequest, session: Session
) -> SalaryPredictionResponse:
    row = (
        (
            await session.execute(
                text(
                    """
                WITH comparable AS (
                  SELECT source, source_snapshot_date, CASE
                    WHEN salary_min IS NOT NULL AND salary_max IS NOT NULL
                      THEN (salary_min + salary_max) / 2
                    ELSE coalesce(salary_min, salary_max)
                  END AS midpoint
                  FROM salary_market_data
                  WHERE true
                    AND title_normalized ILIKE '%' || cast(:title as text) || '%'
                    AND job_level = cast(:level as text)
                    AND location ILIKE '%' || cast(:location as text) || '%'
                    AND (salary_min IS NOT NULL OR salary_max IS NOT NULL)
                    AND (
                      (is_live AND source_snapshot_date >= current_date - interval '6 months')
                      OR (
                        NOT is_live
                        AND source_snapshot_date >= current_date - interval '24 months'
                      )
                    )
                )
                SELECT count(*)::int AS sample_size,
                  percentile_cont(0.25) within group (order by midpoint)::bigint AS p25,
                  percentile_cont(0.50) within group (order by midpoint)::bigint AS median,
                  percentile_cont(0.75) within group (order by midpoint)::bigint AS p75,
                  array_agg(distinct source order by source) AS sources,
                  min(source_snapshot_date) AS period_start,
                  max(source_snapshot_date) AS period_end
                FROM comparable WHERE midpoint BETWEEN 1000000 AND 200000000
                """
                ),
                {"title": payload.title, "level": payload.level, "location": payload.location},
            )
        )
        .mappings()
        .one()
    )
    sample_size = row["sample_size"] or 0
    if sample_size >= 3 and row["median"]:
        return SalaryPredictionResponse(
            salary_estimate=row["median"],
            salary_p25=row["p25"],
            salary_p75=row["p75"],
            sample_size=sample_size,
            source="market_quantiles",
            sources=row["sources"] or [],
            period_start=row["period_start"],
            period_end=row["period_end"],
        )
    model_prediction = await request_published_salary_model(payload)
    if model_prediction is not None:
        return SalaryPredictionResponse(
            **model_prediction,
            sample_size=sample_size,
            source="published_salary_model",
        )
    level_base = {
        "intern": 8_000_000,
        "fresher": 12_000_000,
        "junior": 18_000_000,
        "mid": 30_000_000,
        "senior": 45_000_000,
        "lead": 60_000_000,
        "manager": 70_000_000,
        "director": 90_000_000,
    }.get(payload.level, 30_000_000)
    experience_adjustment = min(payload.experience_years, 15) * 1_200_000
    estimate = int(level_base + experience_adjustment)
    return SalaryPredictionResponse(
        salary_estimate=estimate,
        salary_p25=int(estimate * 0.8),
        salary_p75=int(estimate * 1.2),
        sample_size=sample_size,
        source="cold_start_fallback",
    )


@router.get("/bands", response_model=list[SalaryBand])
async def salary_bands(
    session: Session,
    title: Annotated[str | None, Query(max_length=200)] = None,
    level: str | None = None,
    location: str | None = None,
) -> list[SalaryBand]:
    rows = await session.execute(
        text(
            """
            WITH disclosed AS (
              SELECT title_normalized, job_level, location, source, source_snapshot_date,
                CASE
                  WHEN salary_min IS NOT NULL AND salary_max IS NOT NULL
                    THEN (salary_min + salary_max) / 2
                  ELSE coalesce(salary_min, salary_max)
                END AS midpoint
              FROM salary_market_data
              WHERE (salary_min IS NOT NULL OR salary_max IS NOT NULL)
                AND (
                  cast(:title as text) IS NULL
                  OR title_normalized ILIKE '%' || cast(:title as text) || '%'
                )
                AND (cast(:level as text) IS NULL OR job_level = cast(:level as text))
                AND (
                  cast(:location as text) IS NULL
                  OR location ILIKE '%' || cast(:location as text) || '%'
                )
                AND (
                  (is_live AND source_snapshot_date >= current_date - interval '6 months')
                  OR (
                    NOT is_live
                    AND source_snapshot_date >= current_date - interval '24 months'
                  )
                )
            )
            SELECT title_normalized AS title, job_level AS level, location, count(*) AS sample_size,
              percentile_cont(0.25) within group (order by midpoint)::bigint AS p25,
              percentile_cont(0.50) within group (order by midpoint)::bigint AS median,
              percentile_cont(0.75) within group (order by midpoint)::bigint AS p75,
              array_agg(distinct source order by source) AS sources,
              min(source_snapshot_date) AS period_start,
              max(source_snapshot_date) AS period_end
            FROM disclosed WHERE midpoint BETWEEN 1000000 AND 200000000
            GROUP BY title_normalized, job_level, location HAVING count(*) >= 3
            ORDER BY sample_size DESC LIMIT 50
            """
        ),
        {"title": title, "level": level, "location": location},
    )
    return [SalaryBand.model_validate(dict(row)) for row in rows.mappings()]


@router.get("/benchmark/{title}")
async def salary_benchmark(
    title: str,
    session: Session,
    level: str | None = None,
    location: str | None = None,
) -> dict[str, object]:
    rows = await session.execute(
        text(
            """
            SELECT job_level AS level, location,
              count(*)::int AS sample_size,
              percentile_cont(0.25) WITHIN GROUP (
                ORDER BY coalesce((salary_min + salary_max) / 2, salary_min, salary_max)
              )::bigint AS p25,
              percentile_cont(0.5) WITHIN GROUP (
                ORDER BY coalesce((salary_min + salary_max) / 2, salary_min, salary_max)
              )::bigint AS median,
              percentile_cont(0.75) WITHIN GROUP (
                ORDER BY coalesce((salary_min + salary_max) / 2, salary_min, salary_max)
              )::bigint AS p75,
              array_agg(distinct source order by source) AS sources,
              min(source_snapshot_date) AS period_start,
              max(source_snapshot_date) AS period_end
            FROM salary_market_data
            WHERE title_normalized ILIKE '%' || cast(:title AS text) || '%'
              AND (salary_min IS NOT NULL OR salary_max IS NOT NULL)
              AND (cast(:level AS text) IS NULL OR job_level = cast(:level AS text))
              AND (
                cast(:location AS text) IS NULL
                OR location ILIKE '%' || cast(:location AS text) || '%'
              )
              AND (
                (is_live AND source_snapshot_date >= current_date - interval '6 months')
                OR (
                  NOT is_live
                  AND source_snapshot_date >= current_date - interval '24 months'
                )
              )
            GROUP BY job_level, location
            HAVING count(*) >= 3
            ORDER BY sample_size DESC
            """
        ),
        {"title": title, "level": level, "location": location},
    )
    return {"title": title, "currency": "VND", "segments": [dict(row) for row in rows.mappings()]}
