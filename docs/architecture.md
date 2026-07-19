# Architecture

JobRadar VN is a modular monolith deployed as separate processes. This keeps the
initial operating model simple while preserving explicit boundaries between data
collection, enrichment, analytics and user-facing workloads.

## Runtime flow

1. Celery Beat schedules a source adapter.
2. The adapter checks `robots.txt`, applies a per-domain rate limit and validates
   public posting data before updating the source-grained `raw_jobs` record.
3. NLP workers normalize salary, title and skills into `jobs`.
4. dbt builds stable analytics marts from structured data.
5. FastAPI serves jobs, salary bands and market analytics to the Next.js app.
6. Alert workers evaluate saved criteria separately from ingestion throughput.

PostgreSQL is the only durable application store. Redis is disposable and contains
task queue state and bounded caches. Each external source lives behind an adapter,
so policy or markup changes cannot leak into the core domain model.

Licensed historical salary observations have their own table and provenance.
The `salary_market_data` view unifies them with disclosed live salaries for
benchmarking. Expired listings remain available to the time-bounded salary
dataset without being exposed as active jobs. Repeated collection keeps one
sample per source posting: a payload with no disclosed compensation cannot erase
an earlier valid range, and the earliest observed posting timestamp is retained.
A licensed historical row matching a live source ID is merged into the same
salary sample rather than duplicated across the two stores.

## Security boundaries

CV text and vectors remain in `user_profiles` and are excluded from dbt. CV text
is encrypted with pgcrypto AES-256 before storage; only the API and embedding
worker decrypt it inside an RLS-scoped transaction. API responses use ownership
checks before profile access. PostgreSQL RLS enforces a second ownership boundary
using `app.user_id`, which both processes set locally for every profile
transaction. Production startup rejects default secrets. Uploaded files are
size- and type-checked before text extraction; raw uploads are never retained.

## Decisions

- PostgreSQL 16 plus pgvector instead of a separate vector database.
- HNSW for a dynamically growing embedding collection.
- Cursor pagination for stable job feeds.
- Rule-based salary bands remain the fallback when no approved ML model exists.
- Source adapters default to disabled until collection permission is confirmed.
