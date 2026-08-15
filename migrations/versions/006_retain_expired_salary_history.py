"""Retain disclosed salaries after a public job expires."""

from collections.abc import Sequence

from alembic import op

revision: str = "006_retain_salary_history"
down_revision: str | None = "005_encrypt_cv_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIVE_SALARY_BASE = """
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
"""
LIVE_SALARY_FILTER = "WHERE jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL\n"
ACTIVE_LIVE_SALARY_FILTER = (
    "WHERE jobs.is_active AND (jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL)\n"
)
HISTORICAL_SALARY_UNION = """
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
    _create_view(LIVE_SALARY_BASE + LIVE_SALARY_FILTER + HISTORICAL_SALARY_UNION)


def downgrade() -> None:
    _create_view(LIVE_SALARY_BASE + ACTIVE_LIVE_SALARY_FILTER + HISTORICAL_SALARY_UNION)
