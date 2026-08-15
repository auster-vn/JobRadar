# API contracts

Interactive OpenAPI documentation is available at `/docs`; the machine-readable
schema is at `/openapi.json`. All request and response bodies use JSON unless an
endpoint explicitly accepts multipart form data.

## Authentication

`POST /api/auth/register` and `POST /api/auth/login` set 30-minute access and
seven-day refresh tokens in HttpOnly cookies. API clients may instead send the
access token as `Authorization: Bearer <token>`. Use `POST /api/auth/refresh` to
rotate cookies and `POST /api/auth/logout` to clear them. `GET /api/auth/session`
returns the current user or `null` without emitting an authentication error and
is intended for browser bootstrap; `GET /api/auth/me` remains protected.

Production uses `AUTH_MODE=supabase`: the API mediates Supabase email login and
validates Supabase JWTs. It exposes an OAuth initiation route, but the current
web app has no `/auth/callback` session handoff, so OAuth is not a supported
end-to-end flow yet. Local JWT/password auth remains for development and the
legacy self-hosted path.

## Public market API

- `GET /api/jobs`: cursor-paginated jobs with title, skill, location, level,
  salary and `platform` filters.
- `GET /api/jobs/{id}`: normalized job detail and source provenance.
- `GET /api/jobs/{id}/similar`: nearest active jobs by pgvector cosine distance.
- `GET /api/jobs/trending`: jobs posted during the last seven days.
- `GET /api/salary/bands`: market quartiles grouped by normalized title and level.
- `GET /api/salary/benchmark/{title}`: title segments with a minimum of three samples.
- `POST /api/salary/predict`: market estimate with explicit model or cold-start
  source metadata.
- `GET /api/analytics/skills/demand`: ranked skill demand.
- `GET /api/analytics/skills/trending`: current versus prior 30-day demand.
- `GET /api/analytics/hiring/trends`: company posting velocity.
- `GET /api/analytics/salary/by-skill` and `/salary/by-company-type`: disclosed
  salary medians; segments with fewer than three samples are suppressed.

## User API

- `GET|PUT /api/profile`: private profile preferences and skills.
- `POST /api/profile/cv`: PDF, DOCX or UTF-8 text, at most 5 MB. Extracted text is
  private and never enters analytics models.
- `DELETE /api/profile/cv`: permanently clears the authenticated user's extracted
  CV text and semantic vector while retaining manually curated profile fields.
- `GET /api/profile/matching-jobs`: hybrid skill-overlap and CV cosine ranking,
  with deterministic skill-only fallback until a CV embedding exists.
- `GET /api/profile/skill-gap`: missing skills for a target role and level.
- `POST|GET /api/alerts`, `PUT|DELETE /api/alerts/{id}`: owned alert rules.
- `GET /api/alerts/{id}/history`: last 100 durable delivery attempts.
- `POST /api/jobs/{id}/score`: bounded explainable fit score with a persisted
  provider/model/input-hash cache.
- `GET|POST /api/applications`, `PATCH /api/applications/{id}`: owned
  application tracking and notes.

## Operations API

Routes under `/api/admin` require `X-Admin-Key`. They expose pipeline counts,
scrape batches, queued ITViec, TopCV and VietnamWorks triggers, salary data
readiness and retraining. Never expose this key to browser code. `/health`,
`/health/ready`, `/version` and `/metrics` support container orchestration and
monitoring. `/version` includes the immutable `source_revision` embedded in the
release image so deployment checks can verify the active Git SHA.

`POST /api/cron/daily` is separate from the admin API. It requires
`X-Cron-Secret`, accepts an 8–128 character `Idempotency-Key`, and queues the
tracked pipeline only when a Celery worker is provisioned. The default free
GitHub workflow runs the tracked CLI directly instead.

Anonymous and authenticated clients have separate Redis-backed fixed-window
limits. A limited response is HTTP 429 and includes `Retry-After`. The limiter
fails open when Redis is unavailable so Redis cannot take down the API.
