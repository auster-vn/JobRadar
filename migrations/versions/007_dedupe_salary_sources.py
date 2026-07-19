"""Deduplicate salary observations that also exist as live jobs."""

from collections.abc import Sequence

from alembic import op

revision: str = "007_dedupe_salary_sources"
down_revision: str | None = "006_retain_salary_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEDUPLICATED_VIEW = """
WITH historical_dates AS (
  SELECT
    observations.source,
    observations.source_record_id,
    min(observations.source_snapshot_date) AS first_observed_on
  FROM salary_observations AS observations
  WHERE observations.salary_min IS NOT NULL OR observations.salary_max IS NOT NULL
  GROUP BY observations.source, observations.source_record_id
)
SELECT
  jobs.id::text AS record_id,
  jobs.platform AS source,
  historical_dates.first_observed_on IS NULL AS is_live,
  coalesce(
    least(jobs.posted_at::date, historical_dates.first_observed_on),
    jobs.posted_at::date,
    historical_dates.first_observed_on
  ) AS source_snapshot_date,
  jobs.title_normalized,
  jobs.job_level,
  locations.location,
  coalesce(jobs.experience_years_min, 0) AS experience_years,
  jobs.skills_required AS skills,
  jobs.salary_min,
  jobs.salary_max
FROM jobs
LEFT JOIN historical_dates
  ON historical_dates.source = jobs.platform
 AND historical_dates.source_record_id = jobs.platform_job_id
CROSS JOIN LATERAL unnest(jobs.location) AS locations(location)
WHERE jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL
UNION ALL
SELECT
  observations.id::text,
  observations.source,
  false,
  observations.source_snapshot_date,
  observations.title_normalized,
  observations.job_level,
  observations.location,
  coalesce(observations.experience_years_min, 0),
  observations.skills,
  observations.salary_min,
  observations.salary_max
FROM salary_observations AS observations
WHERE (observations.salary_min IS NOT NULL OR observations.salary_max IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1
    FROM jobs
    WHERE jobs.platform = observations.source
      AND jobs.platform_job_id = observations.source_record_id
      AND (jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL)
  )
"""

PREVIOUS_VIEW = """
SELECT
  jobs.id::text AS record_id,
  jobs.platform AS source,
  true AS is_live,
  jobs.posted_at::date AS source_snapshot_date,
  jobs.title_normalized,
  jobs.job_level,
  locations.location,
  coalesce(jobs.experience_years_min, 0) AS experience_years,
  jobs.skills_required AS skills,
  jobs.salary_min,
  jobs.salary_max
FROM jobs
CROSS JOIN LATERAL unnest(jobs.location) AS locations(location)
WHERE jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL
UNION ALL
SELECT
  observations.id::text,
  observations.source,
  false,
  observations.source_snapshot_date,
  observations.title_normalized,
  observations.job_level,
  observations.location,
  coalesce(observations.experience_years_min, 0),
  observations.skills,
  observations.salary_min,
  observations.salary_max
FROM salary_observations AS observations
WHERE observations.salary_min IS NOT NULL OR observations.salary_max IS NOT NULL
"""


def _create_view(query: str) -> None:
    op.execute("CREATE OR REPLACE VIEW salary_market_data AS " + query)


def upgrade() -> None:
    _create_view(DEDUPLICATED_VIEW)


def downgrade() -> None:
    _create_view(PREVIOUS_VIEW)
