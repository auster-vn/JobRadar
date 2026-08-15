-- Declarative SQL mirror of Alembic revision 008_saas_domains.
-- Alembic remains authoritative; these IF NOT EXISTS statements are a
-- post-migration contract and safe no-ops on a correctly migrated database.

BEGIN;

DO $guard$
DECLARE
  missing_tables text;
BEGIN
  IF to_regclass('public.alembic_version') IS NULL THEN
    RAISE EXCEPTION
      'Alembic must be applied before the managed schema contract';
  END IF;

  SELECT string_agg(required.name, ', ' ORDER BY required.name)
  INTO missing_tables
  FROM unnest(ARRAY[
    'users',
    'user_profiles',
    'jobs',
    'applications',
    'job_scores',
    'pipeline_runs',
    'user_settings',
    'notifications',
    'audit_logs'
  ]) AS required(name)
  WHERE to_regclass('public.' || required.name) IS NULL;

  IF missing_tables IS NOT NULL THEN
    RAISE EXCEPTION
      'Alembic managed-domain tables are missing: %', missing_tables;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user_profiles'
      AND column_name = 'cv_storage_path'
  ) THEN
    RAISE EXCEPTION
      'Alembic managed-domain column user_profiles.cv_storage_path is missing';
  END IF;
END
$guard$;

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS cv_storage_path varchar(1000);

CREATE TABLE IF NOT EXISTS public.applications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  job_id uuid NOT NULL REFERENCES public.jobs(id) ON DELETE RESTRICT,
  status varchar(20) NOT NULL DEFAULT 'saved',
  notes text,
  applied_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_applications_user_job UNIQUE (user_id, job_id),
  CONSTRAINT ck_applications_status CHECK (
    status IN ('saved', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn')
  ),
  CONSTRAINT ck_applications_notes_length CHECK (
    notes IS NULL OR char_length(notes) <= 4000
  )
);
CREATE INDEX IF NOT EXISTS ix_applications_user_updated
  ON public.applications (user_id, updated_at, id);
CREATE INDEX IF NOT EXISTS ix_applications_user_status
  ON public.applications (user_id, status, updated_at, id);

CREATE TABLE IF NOT EXISTS public.job_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  job_id uuid NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
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
  CONSTRAINT uq_job_scores_cache_key UNIQUE (
    user_id, job_id, provider, model_version, input_hash
  ),
  CONSTRAINT ck_job_scores_overall_score CHECK (overall_score BETWEEN 0 AND 100),
  CONSTRAINT ck_job_scores_skill_score CHECK (skill_score BETWEEN 0 AND 100),
  CONSTRAINT ck_job_scores_experience_score CHECK (experience_score BETWEEN 0 AND 100),
  CONSTRAINT ck_job_scores_location_score CHECK (location_score BETWEEN 0 AND 100),
  CONSTRAINT ck_job_scores_input_hash CHECK (input_hash ~ '^[0-9a-f]{64}$')
);
CREATE INDEX IF NOT EXISTS ix_job_scores_user_job_created
  ON public.job_scores (user_id, job_id, created_at);

CREATE TABLE IF NOT EXISTS public.pipeline_runs (
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
  CONSTRAINT uq_pipeline_runs_idempotency_key UNIQUE (idempotency_key),
  CONSTRAINT ck_pipeline_runs_status CHECK (
    status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')
  )
);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_kind_created
  ON public.pipeline_runs (kind, created_at);
CREATE INDEX IF NOT EXISTS ix_pipeline_runs_status_created
  ON public.pipeline_runs (status, created_at);

CREATE TABLE IF NOT EXISTS public.user_settings (
  user_id uuid PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  ai_provider varchar(32) NOT NULL DEFAULT 'deterministic',
  ai_model varchar(128),
  daily_score_budget integer NOT NULL DEFAULT 20,
  notifications_enabled boolean NOT NULL DEFAULT true,
  preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_user_settings_score_budget CHECK (daily_score_budget >= 0)
);

CREATE TABLE IF NOT EXISTS public.notifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  application_id uuid REFERENCES public.applications(id) ON DELETE CASCADE,
  job_id uuid REFERENCES public.jobs(id) ON DELETE CASCADE,
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
  CONSTRAINT ck_notifications_status CHECK (
    status IN ('pending', 'sent', 'failed', 'read')
  )
);
CREATE INDEX IF NOT EXISTS ix_notifications_user_created
  ON public.notifications (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_notifications_user_status
  ON public.notifications (user_id, status);

CREATE TABLE IF NOT EXISTS public.audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
  actor_type varchar(32) NOT NULL DEFAULT 'user',
  action varchar(128) NOT NULL,
  entity_type varchar(64) NOT NULL,
  entity_id uuid,
  request_id varchar(128),
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_created
  ON public.audit_logs (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_entity
  ON public.audit_logs (entity_type, entity_id);

COMMIT;
