"""Add application tracking, scoring, and operational SaaS domains."""

from collections.abc import Sequence

from alembic import op

revision: str = "008_saas_domains"
down_revision: str | None = "007_dedupe_salary_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_EXPRESSION = "user_id = nullif(current_setting('app.user_id', true), '')::uuid"


def _enable_owner_rls(table: str, *, mutable: bool = True) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    if mutable:
        op.execute(
            f"""
            CREATE POLICY {table}_owner_policy ON {table}
            USING ({OWNER_EXPRESSION})
            WITH CHECK ({OWNER_EXPRESSION})
            """
        )
        return
    op.execute(
        f"""
        CREATE POLICY {table}_owner_select_policy ON {table}
        FOR SELECT USING ({OWNER_EXPRESSION})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_owner_insert_policy ON {table}
        FOR INSERT WITH CHECK ({OWNER_EXPRESSION})
        """
    )


def upgrade() -> None:
    op.execute("ALTER TABLE user_profiles ADD COLUMN cv_storage_path varchar(1000)")
    op.execute(
        """
        CREATE TABLE applications (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
          status varchar(20) NOT NULL DEFAULT 'saved',
          notes text,
          applied_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_applications_user_job UNIQUE(user_id, job_id),
          CONSTRAINT ck_applications_status CHECK(
            status IN ('saved', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn')
          ),
          CONSTRAINT ck_applications_notes_length CHECK(
            notes IS NULL OR char_length(notes) <= 4000
          )
        )
        """
    )
    op.execute("CREATE INDEX ix_applications_user_updated ON applications(user_id, updated_at, id)")
    op.execute(
        """
        CREATE INDEX ix_applications_user_status
        ON applications(user_id, status, updated_at, id)
        """
    )

    op.execute(
        """
        CREATE TABLE job_scores (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          provider varchar(32) NOT NULL,
          model_version varchar(128) NOT NULL,
          input_hash varchar(64) NOT NULL,
          overall_score numeric(5,2) NOT NULL,
          skill_score numeric(5,2) NOT NULL,
          experience_score numeric(5,2) NOT NULL,
          location_score numeric(5,2) NOT NULL,
          matched_skills text[] NOT NULL DEFAULT '{}',
          missing_skills text[] NOT NULL DEFAULT '{}',
          summary text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_job_scores_cache_key UNIQUE(
            user_id, job_id, provider, model_version, input_hash
          ),
          CONSTRAINT ck_job_scores_overall_score CHECK(overall_score BETWEEN 0 AND 100),
          CONSTRAINT ck_job_scores_skill_score CHECK(skill_score BETWEEN 0 AND 100),
          CONSTRAINT ck_job_scores_experience_score CHECK(experience_score BETWEEN 0 AND 100),
          CONSTRAINT ck_job_scores_location_score CHECK(location_score BETWEEN 0 AND 100),
          CONSTRAINT ck_job_scores_input_hash CHECK(input_hash ~ '^[0-9a-f]{64}$')
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_job_scores_user_job_created
        ON job_scores(user_id, job_id, created_at)
        """
    )

    op.execute(
        """
        CREATE TABLE pipeline_runs (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          kind varchar(64) NOT NULL,
          source varchar(64),
          status varchar(20) NOT NULL DEFAULT 'queued',
          idempotency_key varchar(128) NOT NULL,
          records_processed integer NOT NULL DEFAULT 0,
          errors jsonb NOT NULL DEFAULT '[]'::jsonb,
          details jsonb NOT NULL DEFAULT '{}'::jsonb,
          started_at timestamptz,
          completed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_pipeline_runs_idempotency_key UNIQUE(idempotency_key),
          CONSTRAINT ck_pipeline_runs_status CHECK(
            status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')
          )
        )
        """
    )
    op.execute("CREATE INDEX ix_pipeline_runs_kind_created ON pipeline_runs(kind, created_at)")
    op.execute("CREATE INDEX ix_pipeline_runs_status_created ON pipeline_runs(status, created_at)")

    op.execute(
        """
        CREATE TABLE user_settings (
          user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          ai_provider varchar(32) NOT NULL DEFAULT 'deterministic',
          ai_model varchar(128),
          daily_score_budget integer NOT NULL DEFAULT 20,
          notifications_enabled boolean NOT NULL DEFAULT true,
          preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_user_settings_score_budget CHECK(daily_score_budget >= 0)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE notifications (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          application_id uuid REFERENCES applications(id) ON DELETE CASCADE,
          job_id uuid REFERENCES jobs(id) ON DELETE CASCADE,
          kind varchar(64) NOT NULL,
          channel varchar(20) NOT NULL DEFAULT 'in_app',
          status varchar(20) NOT NULL DEFAULT 'pending',
          title varchar(300) NOT NULL,
          body text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          read_at timestamptz,
          sent_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_notifications_status CHECK(
            status IN ('pending', 'sent', 'failed', 'read')
          )
        )
        """
    )
    op.execute("CREATE INDEX ix_notifications_user_created ON notifications(user_id, created_at)")
    op.execute("CREATE INDEX ix_notifications_user_status ON notifications(user_id, status)")

    op.execute(
        """
        CREATE TABLE audit_logs (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id uuid REFERENCES users(id) ON DELETE SET NULL,
          actor_type varchar(32) NOT NULL DEFAULT 'user',
          action varchar(128) NOT NULL,
          entity_type varchar(64) NOT NULL,
          entity_id uuid,
          request_id varchar(128),
          details jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_logs_user_created ON audit_logs(user_id, created_at)")
    op.execute("CREATE INDEX ix_audit_logs_entity ON audit_logs(entity_type, entity_id)")

    _enable_owner_rls("applications")
    _enable_owner_rls("job_scores", mutable=False)
    _enable_owner_rls("user_settings")
    _enable_owner_rls("notifications")
    _enable_owner_rls("audit_logs", mutable=False)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS notifications")
    op.execute("DROP TABLE IF EXISTS user_settings")
    op.execute("DROP TABLE IF EXISTS pipeline_runs")
    op.execute("DROP TABLE IF EXISTS job_scores")
    op.execute("DROP TABLE IF EXISTS applications")
    op.execute("ALTER TABLE user_profiles DROP COLUMN IF EXISTS cv_storage_path")
