# Managed operations runbook

This runbook covers the Vercel + Render + Supabase + Upstash deployment. For the
optional Docker/Tailscale/Prometheus topology, use
[SELF_HOSTING.md](SELF_HOSTING.md).

## Service inventory

| Component | Production role | Durable data |
| --- | --- | --- |
| Vercel | Next.js UI and same-origin API rewrites | none |
| Render web | FastAPI, auth mediation, validation, scoring | none |
| Supabase | PostgreSQL, Auth, private Storage | all system-of-record data |
| Upstash | cache, rate limits, optional Celery broker | disposable/transient |
| GitHub Actions | free daily ingestion and alert runner | workflow logs/artifacts |

Keep owner, billing/quota contacts, dashboard links, and key-rotation dates in an
access-controlled operator record. Do not store credentials in this file.

## Health and readiness

```bash
curl --fail https://YOUR-API/health
curl --fail https://YOUR-API/health/ready
curl --fail https://YOUR-API/version
```

- `/health` confirms that the process can serve HTTP.
- `/health/ready` confirms that required schema objects, PostgreSQL, and
  production Redis are available. Render routes readiness to this endpoint.
- `/version` reports the environment and deployed source revision.

Treat a readiness 503 as actionable. The response distinguishes database and
cache failures. A health 200 with readiness 503 is not a healthy release.

Metrics require `METRICS_TOKEN`, or `ADMIN_API_KEY` when no separate metrics
token is configured:

```bash
curl --fail https://YOUR-API/metrics \
  -H "X-Metrics-Token: $METRICS_TOKEN"
```

Prefer a distinct `METRICS_TOKEN` when integrating an external collector.
Never put the token in a query string.

## Logs

Production API logs are structured JSON on stdout. Render is the first place to
inspect:

- startup/migration failures;
- request ID, method, route, status, and latency;
- database pool timeouts;
- upstream Auth/AI/Storage errors;
- cache fallback and rate-limit errors.

Vercel logs cover server-rendering and rewrite failures. GitHub Actions logs
cover scheduled source, alert, and migration failures. Supabase and Upstash
dashboards cover database/Auth/Storage and Redis events respectively.

Logs must not contain:

- authorization/cookie values;
- database or Redis URLs;
- Supabase service-role keys;
- CV text or uploaded files;
- SMTP, provider, admin, metrics, or cron secrets.

If one appears, treat it as credential exposure even if the workflow log is
private.

## Daily pipeline

`.github/workflows/daily-pipeline.yml` runs at 23:00 UTC (06:00 Vietnam time)
and can be dispatched manually. It applies migrations and then runs:

```bash
PIPELINE_IDEMPOTENCY_KEY=daily:YYYY-MM-DD \
  uv run python -m scripts.run_daily_pipeline
```

The CLI:

1. creates or reuses a unique `pipeline_runs` row;
2. runs enabled source ingestion concurrently with source-level isolation;
3. normalizes and deduplicates through database constraints/upserts;
4. bounds active users/jobs, ranks with deterministic no-LLM scoring, and
   persists qualifying top scores plus in-app recommendation notifications;
5. expires stale jobs;
6. evaluates alerts and records delivery results;
7. stores status, processed count, details, and bounded errors.

`completed` and `partial` are terminal and idempotent. A `partial` result
means at least one source or alert stage failed and requires inspection even if
the workflow itself is green. A fatal `failed` result exits nonzero.

Useful SQL:

```sql
select id, status, idempotency_key, records_processed,
       started_at, completed_at, errors
from public.pipeline_runs
order by created_at desc
limit 20;

select platform, status, jobs_found, jobs_new, jobs_updated, errors,
       started_at, completed_at
from public.scrape_batches
order by started_at desc
limit 30;
```

### Rerun policy

1. Fix the external or configuration failure first.
2. Re-run the same workflow. A failed row is reused; a completed/partial daily
   key is not duplicated.
3. If an operator intentionally needs a second run, use a distinct 8–128
   character key such as `daily:2026-08-15:retry-1` from a controlled shell.
4. Confirm unique source keys prevented duplicate jobs and review notification
   deliveries before retrying alerts.

Never delete a `pipeline_runs` row merely to make a workflow rerun.

## Optional queue-trigger mode

`POST /api/cron/daily` is protected only by `X-Cron-Secret` and accepts an
`Idempotency-Key`. It is intended for installations with a continuously
running Celery worker:

```bash
curl --fail-with-body -X POST https://YOUR-API/api/cron/daily \
  -H "X-Cron-Secret: $CRON_SECRET" \
  -H "Idempotency-Key: daily:$(date -u +%F)"
```

Do not substitute `ADMIN_API_KEY`. A 202 means queued, not completed. Check the
returned run ID in `pipeline_runs`. The default free deployment uses the
tracked CLI instead because Render does not provide a free background-worker
instance.

## Source health

Scrapers are disabled until explicitly enabled with repository/environment
variables. For each source:

- retain a monitored contact address in `SCRAPER_CONTACT_EMAIL`;
- review terms and robots policy before enabling;
- use bounded page/detail limits;
- inspect `scrape_batches` and structured result `errors`;
- disable the source immediately on a policy change, sustained block, or markup
  failure;
- do not disguise identity or bypass access controls.

A source returning zero jobs is not automatically healthy. Compare with its
recent baseline and inspect parser fixtures/source responses without committing
copyrighted pages or personal data.

## Database migrations

Every Render start and daily pipeline runs:

1. `alembic upgrade head`
2. `database/schema.sql`

Alembic owns tables/indexes. The second layer is idempotent Supabase
Auth/RLS/Storage reconciliation. Never create the same application table through
the Supabase dashboard.

Before merging a migration:

- run it against a disposable pgvector PostgreSQL database;
- test a clean upgrade and an upgrade from the current production revision;
- verify RLS with two different user IDs;
- assess lock duration and whether old application code remains compatible;
- back up production before destructive or bulk operations.

Inspect revision and required objects:

```sql
select version_num from public.alembic_version;
select to_regclass('public.jobs'),
       to_regclass('public.applications'),
       to_regclass('public.pipeline_runs');
```

Do not automatically downgrade production after code rollback. Prefer a
forward-compatible corrective migration.

## Tenant-isolation checks

Supabase Auth users are projected to `public.users`. Private policies resolve
the owner from `auth.uid()` for PostgREST or transaction-local `app.user_id`
for FastAPI.

After any auth/RLS change, verify:

- user A cannot read or mutate user B's profile, application, settings, scores,
  notifications, alerts, or audit rows;
- anon can read only the intended active catalogue data;
- operational raw jobs, embeddings, scrape batches, pipeline runs, and Alembic
  metadata are not available to anon/authenticated PostgREST callers;
- a candidate can access only Storage objects whose first path segment is their
  UUID;
- the service-role key never appears in Vercel or browser output.

Use a disposable project/user pair for tests. Do not disable RLS to diagnose an
application authorization bug.

## Backups and restore

Supabase is the system of record. Before a risky release:

1. confirm the provider backup/export is recent;
2. export schema plus required data with the direct/session-pooler URL;
3. encrypt any local backup and store it outside the repository;
4. restore into a separate project;
5. run Alembic, the Supabase layer, readiness, and tenant-isolation smoke tests.

Never check in `.dump`, `.backup`, `.sql.gz`, CV files, or database URLs.
The ignore rules are a safety net, not a backup policy.

Storage objects and database metadata are separate. A complete recovery plan
must include the private `candidate-files` bucket and validate object paths
against `user_profiles.cv_storage_path`.

## Secret rotation

Rotate one dependency at a time when practical:

- `JWT_SECRET`: invalidates locally signed sessions; coordinate Render and
  GitHub.
- `ADMIN_API_KEY`: update operators/monitoring and Render/GitHub.
- `CRON_SECRET`: update the optional queue caller and Render; it is not used as
  an admin key.
- `CV_ENCRYPTION_KEY`: requires a planned decrypt/re-encrypt migration; do not
  simply replace it while encrypted rows exist.
- Supabase anon key: update Render and any public frontend value.
- Supabase service-role key: update Render/GitHub immediately; it bypasses RLS.
- Database password: rotate both runtime and migration URLs.
- Upstash token: rotate TCP and REST settings together.
- AI/SMTP/Telegram credentials: revoke at the provider, update server/workflow,
  and redeploy.

After rotation, confirm the old value fails, readiness is green, and no secret
appears in logs.

## Incident triage

### API cold start or 5xx

1. Check Render deploy status and startup logs.
2. Request `/health`, then `/health/ready`.
3. Check Supabase/Upstash status and quotas.
4. Confirm `PORT`, pool settings, CORS, and URL schemes.
5. Redeploy the last known-good revision if application startup changed.

### Database unavailable

1. Confirm the runtime URL uses the transaction pooler and asyncpg scheme.
2. Confirm the migration URL uses a direct/session-pooler endpoint.
3. Check password rotation, project pause, connection limits, and SSL parameters.
4. Keep pool size/overflow small; do not solve saturation by multiplying
   connections across jobs.

### Cache unavailable

Production readiness fails closed because Redis backs rate limits/cache
coordination. Check the `rediss://` URL and
`ssl_cert_reqs=required`, Upstash quota, and token rotation. The database
remains authoritative; never restore Redis as durable data.

### Auth failures

Check `AUTH_MODE=supabase`, project URL, anon key, JWKS reachability, Site URL,
redirect allowlist, and CORS. New projects should not require a shared JWT
secret. Do not switch production to local auth as an incident workaround.

### CV upload failures

Check the service-role key, private bucket, MIME type, 6 MiB limit, UUID path,
and Storage policies. Treat a public bucket or cross-user signed URL as a
security incident.

### Runaway AI cost

Set `AI_PROVIDER=deterministic`, revoke the affected provider key, inspect
`job_scores` cache behavior and provider usage, then redeploy. See
[../AI_PROVIDER.md](../AI_PROVIDER.md).

## Routine maintenance

Daily:

- inspect failed/partial scheduled runs and source health;
- check Render, Supabase, Upstash, Vercel, and Actions quotas.

Weekly:

- review API error/latency trends and readiness incidents;
- review failed notifications and stale queued/running pipeline rows;
- verify dependency/security automation is green.

Monthly:

- test a database/Storage restore;
- review active users, provider access, CORS origins, and repository
  collaborators; review OAuth redirects only after the missing web callback is
  implemented;
- remove unused preview origins and credentials;
- review AI spend and scraper authorization;
- verify all provider free-tier limits and pricing still fit the operating plan.

## Release checklist

- CI passes at the release SHA, including 80% backend coverage, frontend build,
  browser flows, infrastructure validation, and Trivy.
- Render migrates successfully and `/health/ready` returns 200.
- Vercel serves the expected source revision and its API rewrites reach Render.
- Registration/login, profile, Storage, application, and score flows pass.
- The daily workflow completes or has an understood `partial` result.
- Rollback and backup evidence exist for schema-affecting changes.
