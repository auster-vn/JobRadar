# Architecture

JobRadar VN is a modular monolith deployed as separate processes. This keeps the
initial operating model simple while preserving explicit boundaries between data
collection, enrichment, analytics and user-facing workloads.

The primary managed topology is Vercel + Render + Supabase + Upstash with a
tracked GitHub Actions daily runner; see [REFACTOR_PLAN.md](REFACTOR_PLAN.md).
Continuous Celery/ML/analytics processes described below belong to the optional
self-hosted or paid-worker topology.

## Runtime flow

1. GitHub Actions runs the tracked daily CLI on the free path; Celery Beat is an
   optional continuous scheduler.
2. The adapter checks `robots.txt`, applies a per-domain rate limit and validates
   public posting data before updating the source-grained `raw_jobs` record.
3. NLP workers normalize salary, title and skills into `jobs`.
4. dbt builds stable analytics marts from structured data.
5. FastAPI serves jobs, salary bands and market analytics to the Next.js app.
6. Alert workers evaluate saved criteria separately from ingestion throughput.

PostgreSQL is the only durable application store. Redis is disposable and contains
task queue state and bounded caches. Each external source lives behind an adapter,
so policy or markup changes cannot leak into the core domain model.

Provenance-pinned salary observations have their own table and license metadata.
The `salary_market_data` view unifies them with disclosed live salaries for
benchmarking. Expired listings remain available to the time-bounded salary
dataset without being exposed as active jobs. Repeated collection keeps one
sample per source posting: a payload with no disclosed compensation cannot erase
an earlier valid range, and the earliest observed posting timestamp is retained.
A historical row matching a live source ID is merged into the same
salary sample rather than duplicated across the two stores.

Salary publication is release-bound. CI evaluates a manifest-pinned first-seen
cohort; Release reconstructs an empty database from the pinned snapshots,
retrains at the release Git SHA and embeds only a passing artifact in the ML
image. A one-shot service installs it into an immutable revision directory.
Production readiness requires the ML API to load that exact revision.

## Security boundaries

CV text and vectors remain in `user_profiles` and are excluded from dbt. CV text
is encrypted with pgcrypto AES-256; candidate files may be retained in the
private Supabase `candidate-files` bucket under an owner UUID path. Only the API
and embedding worker decrypt profile text inside an RLS-scoped transaction. API
responses use ownership checks before profile access. PostgreSQL RLS accepts
Supabase `auth.uid()` or the API's transaction-local `app.user_id`. Production
startup rejects default secrets. Uploads are size- and type-checked.

## Decisions

- PostgreSQL 16 plus pgvector instead of a separate vector database.
- HNSW for a dynamically growing embedding collection.
- Cursor pagination for stable job feeds.
- Rule-based salary bands remain the fallback when no approved ML model exists.
- Source adapters default to disabled until collection permission is confirmed.
