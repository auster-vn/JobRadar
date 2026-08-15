-- Managed Supabase hardening for the Alembic-managed JobRadar schema.
-- Safe to rerun. Apply only after: alembic upgrade head

BEGIN;

DO $guard$
DECLARE
  missing_tables text;
BEGIN
  IF to_regnamespace('auth') IS NULL OR to_regnamespace('storage') IS NULL THEN
    RAISE EXCEPTION
      'Supabase auth/storage schemas are missing; run this migration on a Supabase project';
  END IF;

  IF to_regclass('public.alembic_version') IS NULL THEN
    RAISE EXCEPTION
      'Alembic must be applied before the Supabase hardening migration';
  END IF;

  SELECT string_agg(required.name, ', ' ORDER BY required.name)
  INTO missing_tables
  FROM unnest(ARRAY[
    'users',
    'user_profiles',
    'jobs',
    'job_scores',
    'applications',
    'pipeline_runs',
    'user_settings',
    'notifications',
    'audit_logs',
    'job_alerts',
    'alert_events',
    'companies',
    'salary_observations',
    'raw_jobs',
    'job_embeddings',
    'scrape_batches'
  ]) AS required(name)
  WHERE to_regclass('public.' || required.name) IS NULL;

  IF missing_tables IS NOT NULL THEN
    RAISE EXCEPTION 'Required application tables are missing: %', missing_tables;
  END IF;
END
$guard$;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Resolve an owner in either execution mode:
-- Supabase/PostgREST supplies auth.uid(); FastAPI sets app.user_id per transaction.
CREATE OR REPLACE FUNCTION public.request_user_id()
RETURNS uuid
LANGUAGE sql
STABLE
SET search_path = ''
AS $function$
  SELECT coalesce(
    auth.uid(),
    nullif(current_setting('app.user_id', true), '')::uuid
  )
$function$;

REVOKE ALL ON FUNCTION public.request_user_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.request_user_id() TO anon, authenticated;

-- public.users is the application projection of Supabase Auth identities.
DO $constraint$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'users_auth_user_fkey'
      AND conrelid = 'public.users'::regclass
  ) THEN
    ALTER TABLE public.users
      ADD CONSTRAINT users_auth_user_fkey
      FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE
      NOT VALID;
  END IF;
END
$constraint$;

ALTER TABLE public.users VALIDATE CONSTRAINT users_auth_user_fkey;

CREATE OR REPLACE FUNCTION public.sync_auth_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
  IF new.email IS NULL THEN
    RAISE EXCEPTION 'JobRadar requires an email-backed Supabase identity';
  END IF;

  INSERT INTO public.users (id, email, password_hash, is_active, created_at, updated_at)
  VALUES (new.id, new.email, '!supabase-managed', true, now(), now())
  ON CONFLICT (id) DO UPDATE
    SET email = excluded.email,
        is_active = true,
        updated_at = now();
  RETURN new;
END
$function$;

DROP TRIGGER IF EXISTS on_auth_user_changed ON auth.users;
CREATE TRIGGER on_auth_user_changed
AFTER INSERT OR UPDATE OF email ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.sync_auth_user();

INSERT INTO public.users (id, email, password_hash, is_active, created_at, updated_at)
SELECT id, email, '!supabase-managed', true, created_at, now()
FROM auth.users
WHERE email IS NOT NULL
ON CONFLICT (id) DO UPDATE
  SET email = excluded.email,
      is_active = true,
      updated_at = now();

-- Public catalogue data is read-only through Supabase. Operational ingestion data
-- remains server-only because no anon/authenticated policies are granted.
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.salary_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.raw_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scrape_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS companies_public_read ON public.companies;
CREATE POLICY companies_public_read ON public.companies
FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS jobs_public_read ON public.jobs;
CREATE POLICY jobs_public_read ON public.jobs
FOR SELECT TO anon, authenticated USING (is_active);

DROP POLICY IF EXISTS salary_observations_public_read ON public.salary_observations;
CREATE POLICY salary_observations_public_read ON public.salary_observations
FOR SELECT TO anon, authenticated USING (true);

-- User-owned tables. Existing Alembic app.user_id policies are replaced with
-- dual-mode policies that also understand Supabase JWT claims.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS users_owner_select ON public.users;
DROP POLICY IF EXISTS users_owner_update ON public.users;
CREATE POLICY users_owner_select ON public.users
FOR SELECT
USING (id = public.request_user_id());
CREATE POLICY users_owner_update ON public.users
FOR UPDATE
USING (id = public.request_user_id())
WITH CHECK (id = public.request_user_id());

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_profiles FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_profiles_owner_policy ON public.user_profiles;
CREATE POLICY user_profiles_owner_policy ON public.user_profiles
FOR ALL
USING (user_id = public.request_user_id())
WITH CHECK (user_id = public.request_user_id());

ALTER TABLE public.job_alerts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS job_alerts_owner_policy ON public.job_alerts;
CREATE POLICY job_alerts_owner_policy ON public.job_alerts
FOR ALL
USING (user_id = public.request_user_id())
WITH CHECK (user_id = public.request_user_id());

ALTER TABLE public.alert_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS alert_events_owner_select ON public.alert_events;
CREATE POLICY alert_events_owner_select ON public.alert_events
FOR SELECT
USING (
  EXISTS (
    SELECT 1
    FROM public.job_alerts
    WHERE job_alerts.id = alert_events.alert_id
      AND job_alerts.user_id = public.request_user_id()
  )
);

ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.applications FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS applications_owner_policy ON public.applications;
CREATE POLICY applications_owner_policy ON public.applications
FOR ALL
USING (user_id = public.request_user_id())
WITH CHECK (user_id = public.request_user_id());

ALTER TABLE public.job_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_scores FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS job_scores_owner_select_policy ON public.job_scores;
DROP POLICY IF EXISTS job_scores_owner_insert_policy ON public.job_scores;
CREATE POLICY job_scores_owner_select_policy ON public.job_scores
FOR SELECT
USING (user_id = public.request_user_id());
CREATE POLICY job_scores_owner_insert_policy ON public.job_scores
FOR INSERT
WITH CHECK (user_id = public.request_user_id());

ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_settings_owner_policy ON public.user_settings;
CREATE POLICY user_settings_owner_policy ON public.user_settings
FOR ALL
USING (user_id = public.request_user_id())
WITH CHECK (user_id = public.request_user_id());

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notifications_owner_policy ON public.notifications;
CREATE POLICY notifications_owner_policy ON public.notifications
FOR ALL
USING (user_id = public.request_user_id())
WITH CHECK (user_id = public.request_user_id());

ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_logs_owner_select_policy ON public.audit_logs;
DROP POLICY IF EXISTS audit_logs_owner_insert_policy ON public.audit_logs;
CREATE POLICY audit_logs_owner_select_policy ON public.audit_logs
FOR SELECT
USING (user_id = public.request_user_id());
CREATE POLICY audit_logs_owner_insert_policy ON public.audit_logs
FOR INSERT
WITH CHECK (user_id = public.request_user_id());

-- Start from least privilege because public is an exposed Supabase schema.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon, authenticated;
GRANT USAGE ON SCHEMA public TO anon, authenticated;

GRANT SELECT ON public.companies, public.jobs, public.salary_observations
  TO anon, authenticated;
GRANT SELECT (id, email, telegram_id, is_active, created_at, updated_at)
  ON public.users TO authenticated;
GRANT UPDATE (telegram_id) ON public.users TO authenticated;
GRANT SELECT (
  user_id, current_title, experience_years, skills, current_salary, target_salary,
  preferred_locations, preferred_job_types, cv_storage_path, updated_at
) ON public.user_profiles TO authenticated;
GRANT INSERT (
  user_id, current_title, experience_years, skills, current_salary, target_salary,
  preferred_locations, preferred_job_types, cv_storage_path
) ON public.user_profiles TO authenticated;
GRANT UPDATE (
  current_title, experience_years, skills, current_salary, target_salary,
  preferred_locations, preferred_job_types, cv_storage_path
) ON public.user_profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.job_alerts TO authenticated;
GRANT SELECT ON public.alert_events TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.applications TO authenticated;
GRANT SELECT ON public.job_scores TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_settings TO authenticated;
GRANT SELECT ON public.notifications TO authenticated;
GRANT UPDATE (status, read_at) ON public.notifications TO authenticated;
GRANT SELECT ON public.audit_logs TO authenticated;

-- Views use the caller's RLS policies rather than the view owner's privileges.
DO $view_security$
BEGIN
  IF to_regclass('public.salary_market_data') IS NOT NULL THEN
    ALTER VIEW public.salary_market_data SET (security_invoker = true);
    GRANT SELECT ON public.salary_market_data TO anon, authenticated;
  END IF;
END
$view_security$;

-- One private bucket. Object keys must start with the authenticated user's UUID.
INSERT INTO storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
VALUES (
  'candidate-files',
  'candidate-files',
  false,
  6291456,
  ARRAY[
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'text/csv',
    'application/json'
  ]
)
ON CONFLICT (id) DO UPDATE
SET public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

DROP POLICY IF EXISTS candidate_files_select_own ON storage.objects;
DROP POLICY IF EXISTS candidate_files_insert_own ON storage.objects;
DROP POLICY IF EXISTS candidate_files_update_own ON storage.objects;
DROP POLICY IF EXISTS candidate_files_delete_own ON storage.objects;

CREATE POLICY candidate_files_select_own ON storage.objects
FOR SELECT TO authenticated
USING (
  bucket_id = 'candidate-files'
  AND (storage.foldername(name))[1] = auth.uid()::text
);
CREATE POLICY candidate_files_insert_own ON storage.objects
FOR INSERT TO authenticated
WITH CHECK (
  bucket_id = 'candidate-files'
  AND (storage.foldername(name))[1] = auth.uid()::text
);
CREATE POLICY candidate_files_update_own ON storage.objects
FOR UPDATE TO authenticated
USING (
  bucket_id = 'candidate-files'
  AND (storage.foldername(name))[1] = auth.uid()::text
)
WITH CHECK (
  bucket_id = 'candidate-files'
  AND (storage.foldername(name))[1] = auth.uid()::text
);
CREATE POLICY candidate_files_delete_own ON storage.objects
FOR DELETE TO authenticated
USING (
  bucket_id = 'candidate-files'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

COMMENT ON TABLE public.users IS 'Application projection of Supabase Auth users.';
COMMENT ON TABLE public.user_profiles IS 'Private candidate profiles and CV references.';
COMMENT ON TABLE public.jobs IS 'Normalized job catalogue.';
COMMENT ON TABLE public.job_scores IS 'Cached per-user job scoring results.';
COMMENT ON TABLE public.applications IS 'Per-user application tracker.';
COMMENT ON TABLE public.pipeline_runs IS 'Operational history for scheduled pipelines.';
COMMENT ON TABLE public.user_settings IS 'Per-user AI and notification preferences.';
COMMENT ON TABLE public.notifications IS 'In-app and external notification records.';
COMMENT ON TABLE public.audit_logs IS 'Append-only security and domain audit events.';

NOTIFY pgrst, 'reload schema';

COMMIT;
