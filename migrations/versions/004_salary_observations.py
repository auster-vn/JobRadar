"""Add licensed historical salary observations."""

from collections.abc import Sequence

from alembic import op

revision: str = "004_salary_observations"
down_revision: str | None = "003_profile_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE salary_observations (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          source varchar(64) NOT NULL,
          source_record_id varchar(64) NOT NULL,
          source_snapshot_date date NOT NULL,
          title varchar(300) NOT NULL,
          title_normalized varchar(300) NOT NULL,
          job_level varchar(32),
          location varchar(160),
          experience_years_min integer,
          experience_years_max integer,
          skills text[] DEFAULT '{}',
          salary_min numeric(15,2),
          salary_max numeric(15,2),
          category varchar(200),
          source_metadata jsonb,
          created_at timestamptz DEFAULT now(),
          CONSTRAINT uq_salary_observation_source_id UNIQUE(source, source_record_id),
          CONSTRAINT ck_salary_observation_min CHECK(salary_min IS NULL OR salary_min > 0),
          CONSTRAINT ck_salary_observation_max CHECK(salary_max IS NULL OR salary_max > 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_salary_observations_title ON salary_observations(title_normalized)")
    op.execute(
        "CREATE INDEX ix_salary_observations_segment ON salary_observations"
        "(job_level, location, source_snapshot_date DESC)"
    )
    op.execute(
        """
        CREATE VIEW salary_market_data AS
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
        WHERE jobs.is_active
          AND (jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL)
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
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS salary_market_data")
    op.execute("DROP TABLE IF EXISTS salary_observations")
