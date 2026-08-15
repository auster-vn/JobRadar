# Managed deployment

This is the primary production path. It uses Vercel, one Render free web
service, Supabase, Upstash, and GitHub Actions. No database, Redis, browser, or
worker must run on an operator's machine.

The optional continuous Celery topology is not part of the free deployment;
see [Continuous workers](#continuous-workers-optional) and
[docs/SELF_HOSTING.md](docs/SELF_HOSTING.md).

## 1. Prerequisites

Create accounts or organizations for:

- GitHub (fork/push this repository and enable Actions)
- Supabase
- Upstash
- Render
- Vercel

Protect the repository's default branch with the `CI` workflow. Do not paste
production secrets into `.env`, Vercel build logs, issue bodies, or workflow
YAML.

Generate four independent secrets. For example:

```bash
openssl rand -hex 32  # JWT_SECRET
openssl rand -hex 32  # ADMIN_API_KEY
openssl rand -hex 32  # CV_ENCRYPTION_KEY
openssl rand -hex 32  # CRON_SECRET
```

Production startup rejects short, default, or duplicated values.

## 2. Create Supabase

1. Create a project in the nearest practical region.
2. In **Project Settings > API**, copy:
   - Project URL → `SUPABASE_URL`
   - anon/public key → `SUPABASE_KEY`
   - service-role key → `SUPABASE_SERVICE_ROLE_KEY` (server only)
3. In the **Connect** panel, copy two PostgreSQL connection strings:
   - transaction pooler, port 6543 → `DATABASE_URL`
   - direct connection or session pooler, port 5432 →
     `MIGRATION_DATABASE_URL`
4. Change the URL scheme from `postgresql://` to
   `postgresql+asyncpg://` for both application settings. Retain
   `sslmode=require` if it is present.

Example shapes (placeholders only):

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres.PROJECT:PASSWORD@POOLER:6543/postgres?sslmode=require
MIGRATION_DATABASE_URL=postgresql+asyncpg://postgres.PROJECT:PASSWORD@POOLER:5432/postgres?sslmode=require
```

The runtime pool is intentionally small and asyncpg's statement cache defaults
to zero for transaction-pooler compatibility. Alembic uses the migration URL.

Do not manually create application tables. Render runs:

```bash
alembic upgrade head
psql "${MIGRATION_DATABASE_URL/postgresql+asyncpg:/postgresql:}" \
  -v ON_ERROR_STOP=1 -f database/schema.sql
```

The second command converts only the SQLAlchemy driver-qualified scheme to a
libpq-compatible scheme. It synchronizes Supabase Auth users, installs RLS and grants, and creates
the private `candidate-files` Storage bucket. It is idempotent and aborts if
Alembic has not yet created the 008 managed-domain schema.

For email login, configure the Supabase Auth Site URL after Vercel assigns the
production URL. The API has an OAuth initiation route, but the current web app
does not implement `/auth/callback` or the browser-to-API session handoff. Do
not enable OAuth providers or advertise an OAuth redirect until that callback
flow is implemented and tested. Email/password authentication is the supported
managed flow.

New Supabase projects are verified through JWKS. Set `SUPABASE_JWT_SECRET`
only for a legacy HS256 project that actually exposes that secret.

## 3. Create Upstash Redis

Create a regional Redis database and copy:

- the TLS TCP connection to `REDIS_URL`;
- the REST URL to `UPSTASH_REDIS_REST_URL`;
- the REST token to `UPSTASH_REDIS_REST_TOKEN`.

Use the TLS Celery/redis-py form recommended by Upstash:

```dotenv
REDIS_URL=rediss://default:TOKEN@HOST:6379?ssl_cert_reqs=required
```

`REDIS_URL` is required because production readiness checks Redis and optional
Celery uses it as broker/result backend. REST credentials are optional; when
present, normal cache operations can use the lower-overhead HTTP transport.

## 4. Deploy the API to Render

Use **New > Blueprint** and select this repository. Render detects
`render.yaml` and builds `docker/backend.Dockerfile`.

Provide the prompted values:

| Setting | Value |
| --- | --- |
| `DATABASE_URL` | Supabase transaction-pooler asyncpg URL |
| `MIGRATION_DATABASE_URL` | Supabase direct/session-pooler asyncpg URL |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | server-only service-role key |
| `REDIS_URL` | Upstash TLS TCP URL |
| `CORS_ORIGINS` | exact comma-separated Vercel origins |

The Blueprint generates `JWT_SECRET`, `ADMIN_API_KEY`,
`CV_ENCRYPTION_KEY`, `CRON_SECRET`, and a distinct `METRICS_TOKEN`. Save
the application secrets in your password manager and copy the required four to
the GitHub `production` environment. Render values created with
`generateValue` are not automatically available to GitHub.

Add these optional Render secrets manually when used:

- `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`
- `SUPABASE_JWT_SECRET` for legacy HS256 only
- exactly one or more AI provider keys documented in
  [AI_PROVIDER.md](AI_PROVIDER.md)
- SMTP/Telegram settings for alert delivery

The release command applies Alembic and the Supabase layer before starting
Uvicorn on Render's `PORT`. Auto-deploy waits for GitHub checks, and Render
uses `/health/ready` as its readiness path.

Record the resulting origin:

```text
https://jobradar-api.onrender.com
```

Do not include a trailing slash in API URL settings.

## 5. Deploy the frontend to Vercel

Import the repository as a Vercel project. Keep the repository root as the
project root; root `vercel.json` runs npm inside `web/`.

Set these for Production, Preview, and Development as appropriate:

```dotenv
API_INTERNAL_URL=https://YOUR-RENDER-SERVICE.onrender.com
NEXT_PUBLIC_API_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

Both are intentional:

- `API_INTERNAL_URL` is used by server rendering and Next.js rewrites.
- `NEXT_PUBLIC_API_URL` is the browser-visible fallback and build-time value.

If a future frontend feature talks directly to Supabase, it may also use:

```dotenv
NEXT_PUBLIC_SUPABASE_URL=https://PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=PUBLIC_ANON_KEY
```

The anon key is designed to be public and is constrained by RLS. Never expose
`SUPABASE_SERVICE_ROLE_KEY`.

Deploy Vercel, then update:

1. Render `CORS_ORIGINS` with the exact production/preview origins you allow.
2. Supabase Auth Site URL and redirect allowlist.
3. Vercel API variables if the Render service name changed.

Redeploy both services after environment changes.

## 6. Configure the free daily worker

The default scheduler is
`.github/workflows/daily-pipeline.yml`. At `23:00 UTC` it runs at `06:00`
in Vietnam. GitHub Actions installs the base and scraping dependencies, applies
database migrations, and runs:

```bash
PIPELINE_IDEMPOTENCY_KEY=daily:YYYY-MM-DD \
  uv run python -m scripts.run_daily_pipeline
```

The CLI writes/reuses a `pipeline_runs` record, fetches/deduplicates jobs, runs
bounded deterministic scoring, persists up to five qualifying recommendations
per user as scores/in-app notifications, expires old jobs, evaluates alerts,
isolates stage failures, and exits nonzero on a fatal failure. It deliberately
does not require a continuously running Celery worker or paid LLM.

Create a GitHub environment named `production`. Add:

Required secrets:

- `DATABASE_URL`
- `MIGRATION_DATABASE_URL`
- `REDIS_URL`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `JWT_SECRET`
- `ADMIN_API_KEY`
- `CV_ENCRYPTION_KEY`
- `CRON_SECRET`

Optional secrets:

- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `SMTP_HOST`, `SMTP_USER`, and `SMTP_PASSWORD`

Repository/environment variables:

- `CORS_ORIGINS`
- `SCRAPER_USER_AGENT`
- `SCRAPER_CONTACT_EMAIL`
- `ENABLE_ITVIEC_SCRAPER`
- `ENABLE_TOPCV_SCRAPER`
- `ENABLE_VIETNAMWORKS_SCRAPER`
- `SMTP_PORT`
- `DAILY_RECOMMENDATION_USER_LIMIT` (default 50)
- `DAILY_RECOMMENDATION_JOB_LIMIT` (default 50)
- `DAILY_RECOMMENDATIONS_PER_USER` (default 5)
- `DAILY_RECOMMENDATION_MIN_SCORE` (default 65)

All scraper flags default to `false`. Enable a source only after reviewing its
terms, robots policy, request limits, and contact information. Trigger
**Daily managed pipeline** manually once and inspect its summary before relying
on the schedule.

## 7. Smoke test

Replace the origins below:

```bash
curl --fail https://YOUR-API/health
curl --fail https://YOUR-API/health/ready
curl --fail https://YOUR-API/version
curl --fail https://YOUR-WEB/
curl --fail https://YOUR-WEB/jobs
```

Expected readiness is HTTP 200 with both database and cache marked available.
A 503 is a real deployment failure; inspect Render logs before continuing.

Test registration/login, profile update, CV upload/delete, job browsing,
application tracking, and two score requests for the same job. The second score
should reuse the persisted cache entry.

## Continuous workers (optional)

`POST /api/cron/daily` is an authenticated queue trigger for a deployment that
has a continuously running Celery worker:

```bash
curl --fail-with-body -X POST https://YOUR-API/api/cron/daily \
  -H "X-Cron-Secret: $CRON_SECRET" \
  -H "Idempotency-Key: daily:$(date -u +%F)"
```

It does not accept `ADMIN_API_KEY` as cron authentication. The endpoint
enqueues work; without a worker, the run cannot progress.

Render does not offer a free background-worker instance. If you intentionally
accept a paid worker or use another provider, run a worker-capable image with:

```bash
celery -A workers.celery_app worker \
  -Q scraping,alerts,nlp,analytics --concurrency=1 --loglevel=info
```

Install the scraping/analytics/NLP extras and Chromium needed by the queues, and
size memory for the selected NLP model. Do not add a paid worker to the default
Blueprint accidentally. The legacy Compose stack already separates the
lightweight and ML worker queues.

## Rollback

- Frontend: promote the previous Vercel deployment.
- API: use Render's rollback/redeploy for the previous image revision.
- Database: do not automatically run `alembic downgrade` after a code rollback.
  Keep application releases backward-compatible with the migrated schema.
- Before destructive migrations, take a Supabase backup/export and test restore
  in a separate project.
- If a key was exposed, rotate it at the provider and in Render/GitHub/Vercel;
  redeploy before considering the incident closed.

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for alerts, incident triage, key
rotation, and recurring maintenance.

## Free-tier constraints

- Render free web services can sleep after inactivity; cold starts are expected.
- Free quotas, regions, and product limits can change. Verify provider dashboards
  before launch.
- Supabase free projects may pause after inactivity and have storage/egress
  limits.
- Upstash commands and bandwidth are metered.
- GitHub-hosted browser jobs consume Actions minutes on private repositories.
- OAuth is not wired in the current web app; a callback/session handoff must be
  implemented before a provider is enabled.
- Custom domains, email reputation, and legal source access still require
  operator-owned configuration.
