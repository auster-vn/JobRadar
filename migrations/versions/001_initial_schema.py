"""Create the complete JobRadar domain schema."""

from collections.abc import Sequence

from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    schema_sql = """
        CREATE TABLE raw_jobs (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(), platform varchar(32) NOT NULL,
          platform_job_id varchar(200) NOT NULL, raw_html text, raw_json jsonb,
          scraped_at timestamptz NOT NULL DEFAULT now(), processed boolean DEFAULT false,
          error text, CONSTRAINT uq_raw_job_source_id UNIQUE(platform, platform_job_id)
        );
        CREATE INDEX ix_raw_jobs_unprocessed ON raw_jobs(processed, scraped_at)
          WHERE processed = false;

        CREATE TABLE companies (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name varchar(300) NOT NULL,
          name_normalized varchar(300) NOT NULL UNIQUE, industry varchar(160),
          company_size varchar(32), company_type varchar(32), website varchar(500),
          logo_url varchar(1000), created_at timestamptz DEFAULT now(),
          updated_at timestamptz DEFAULT now()
        );
        CREATE INDEX ix_companies_name_trgm ON companies
          USING gin(name_normalized gin_trgm_ops);

        CREATE TABLE jobs (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(), raw_job_id uuid REFERENCES raw_jobs(id),
          platform varchar(32) NOT NULL, platform_job_id varchar(200) NOT NULL,
          source_url varchar(1200), company_id uuid NOT NULL REFERENCES companies(id),
          title varchar(300) NOT NULL, title_normalized varchar(300), job_level varchar(32),
          job_type varchar(32), location text[] DEFAULT '{}', salary_min numeric(15,2),
          salary_max numeric(15,2), salary_negotiable boolean DEFAULT false,
          salary_currency varchar(3) DEFAULT 'VND', description_raw text,
          description_cleaned text, skills_required text[] DEFAULT '{}',
          skills_nice_to_have text[] DEFAULT '{}', experience_years_min integer,
          experience_years_max integer, posted_at timestamptz, expires_at timestamptz,
          is_active boolean DEFAULT true, created_at timestamptz DEFAULT now(),
          updated_at timestamptz DEFAULT now(),
          CONSTRAINT uq_job_source_id UNIQUE(platform, platform_job_id),
          CONSTRAINT ck_job_salary_min CHECK(salary_min IS NULL OR salary_min > 0),
          CONSTRAINT ck_job_salary_max CHECK(salary_max IS NULL OR salary_max > 0)
        );
        CREATE INDEX ix_jobs_posted_id ON jobs(posted_at DESC, id DESC);
        CREATE INDEX ix_jobs_level_posted ON jobs(job_level, posted_at DESC);
        CREATE INDEX ix_jobs_title_normalized ON jobs(title_normalized);
        CREATE INDEX ix_jobs_skills_gin ON jobs USING gin(skills_required);
        CREATE INDEX ix_jobs_location_gin ON jobs USING gin(location);
        CREATE INDEX ix_jobs_fts ON jobs USING gin(
          to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description_cleaned, ''))
        );

        CREATE TABLE job_embeddings (
          job_id uuid PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
          embedding vector(384) NOT NULL,
          model_name varchar(200) NOT NULL DEFAULT 'all-MiniLM-L6-v2',
          created_at timestamptz DEFAULT now()
        );
        CREATE INDEX ix_job_embeddings_hnsw ON job_embeddings
          USING hnsw(embedding vector_cosine_ops) WITH (m=16, ef_construction=64);

        CREATE TABLE users (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email varchar(320) NOT NULL UNIQUE,
          password_hash varchar(500) NOT NULL, telegram_id bigint UNIQUE,
          is_active boolean DEFAULT true, created_at timestamptz DEFAULT now(),
          updated_at timestamptz DEFAULT now()
        );
        CREATE TABLE user_profiles (
          user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          current_title varchar(300), experience_years integer, skills text[] DEFAULT '{}',
          current_salary numeric(15,2), target_salary numeric(15,2),
          preferred_locations text[] DEFAULT '{}', preferred_job_types text[] DEFAULT '{}',
          cv_text text, cv_embedding vector(384), updated_at timestamptz DEFAULT now()
        );
        CREATE TABLE job_alerts (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          name varchar(120) NOT NULL DEFAULT 'Job alert', required_skills text[] DEFAULT '{}',
          min_salary numeric(15,2), job_levels text[] DEFAULT '{}', locations text[] DEFAULT '{}',
          skill_match_min_pct numeric(5,2) DEFAULT 60, channel varchar(20) DEFAULT 'email',
          is_active boolean DEFAULT true, last_triggered_at timestamptz,
          created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
        );
        CREATE TABLE scrape_batches (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(), platform varchar(32) NOT NULL,
          started_at timestamptz DEFAULT now(), completed_at timestamptz,
          jobs_found integer DEFAULT 0, jobs_new integer DEFAULT 0,
          jobs_updated integer DEFAULT 0, errors integer DEFAULT 0,
          status varchar(20) DEFAULT 'running'
        );
        """
    for statement in schema_sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS scrape_batches, job_alerts, user_profiles, users, "
        "job_embeddings, jobs, companies, raw_jobs CASCADE"
    )
