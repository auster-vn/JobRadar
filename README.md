# JobRadar VN

[![CI](https://github.com/auster-vn/JobRadar/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/auster-vn/JobRadar/actions/workflows/ci.yml)
[![Release](https://github.com/auster-vn/JobRadar/actions/workflows/release.yml/badge.svg?branch=main)](https://github.com/auster-vn/JobRadar/actions/workflows/release.yml)
[![Deploy](https://github.com/auster-vn/JobRadar/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/auster-vn/JobRadar/actions/workflows/deploy.yml)

Vietnamese technology job-market intelligence built around traceable data,
deterministic normalization, and explicit release gates.

JobRadar VN collects permitted public job postings, normalizes titles, skills,
experience, and disclosed salaries, then serves job discovery, market analytics,
salary benchmarks, matching, and alerts through a FastAPI API and a Vietnamese
Next.js dashboard.

> **Project status:** production-ready for the private single-operator target.
> A revision is accepted only after CI, release retraining, all three immutable
> image builds and security reports, self-hosted deployment, migration, health
> checks, private HTTPS smoke, backup verification, and production browser E2E
> pass for that same revision. The published salary model has 11.88% MAPE
> against the fixed 15% maximum with `data_readiness=true`. Production is
> tailnet-only at <https://jobradar-production.tail92479f.ts.net>. See the
> [completion audit](docs/completion_audit.md) for measured evidence and the
> workflow badges above for current `main`.

## Capabilities

| Area | What is implemented |
|---|---|
| Job discovery | Cursor-paginated search with title, skill, location, level, salary, and source filters |
| Data collection | Robots-aware, fail-closed adapters for ITViec, TopCV, VietnamWorks, and the official LinkedIn API path; scheduled production collection is enabled for the three reviewed sources |
| NLP | Bilingual title normalization, experience parsing, salary normalization, and a versioned 3,336-entry skill taxonomy |
| Market intelligence | Hiring trends, skill demand, salary bands, company activity, and dbt-backed analytics marts |
| Personalization | Encrypted CV extraction, pgvector similarity, deterministic skill matching, and role-level skill-gap analysis |
| Salary intelligence | Observed market quantiles plus a leakage-safe quantile model that is served only after publication gates pass |
| Alerts | Owned alert rules, scheduled matching, durable delivery history, and optional email or Telegram delivery |
| Operations | Prometheus metrics, Grafana dashboards, MLflow tracking, backups, rate limiting, health probes, and rollback-aware CD |

## Measured Status

The repository distinguishes implemented behavior from production claims.
Current acceptance results are recorded in
[`docs/completion_audit.md`](docs/completion_audit.md).

| Gate | Result |
|---|---:|
| Backend unit and integration tests | 287 passed |
| Combined API, NLP, scraper, and ML coverage | 81% |
| dbt build | 32/32 passed |
| Isolated `/api/jobs` load test | 100 RPS target, 8.37 ms p95, 0% HTTP failures |
| Frontend E2E | 3 Playwright workflows passed in CI and directly against production on desktop/mobile paths |
| Salary publication | Pass in CI, release and production: 11.88% MAPE vs. 15% maximum; readiness pass |
| Dependency security | Python audit and npm audit report zero known dependency vulnerabilities |
| Release image security | Every image publishes a Trivy JSON artifact; secrets and every remediable High/Critical finding fail release |
| GitHub CI | The [CI workflow](https://github.com/auster-vn/JobRadar/actions/workflows/ci.yml) must pass every job for the release SHA |
| Release model and images | The [Release workflow](https://github.com/auster-vn/JobRadar/actions/workflows/release.yml) must pass at the same SHA |
| Live production deployment | The [Deploy workflow](https://github.com/auster-vn/JobRadar/actions/workflows/deploy.yml) must pass private smoke at the Tailscale URL |

## Architecture

JobRadar is a modular monolith deployed as independently executable web, API,
worker, analytics, and ML processes. PostgreSQL is the durable source of truth;
Redis holds disposable queue and cache state.

```mermaid
flowchart LR
    S[Permitted job sources] --> C[Source adapters]
    B[Celery Beat] --> C
    C --> P[(PostgreSQL 16 + pgvector)]
    C --> Q[Celery workers]
    Q --> P
    P --> D[dbt models]
    D --> P
    P --> A[FastAPI]
    R[(Redis 7)] <--> A
    R <--> Q
    A --> W[Next.js dashboard]
    P --> M[ML worker]
    M --> F[MLflow]
    M --> G[Gated model artifacts]
    G --> I[Internal ML API]
    I --> A
    A --> O[Prometheus / Grafana]
    Q --> O
```

The detailed runtime flow, security boundaries, and architectural decisions are
documented in [`docs/architecture.md`](docs/architecture.md).

## Technology Stack

| Layer | Technologies |
|---|---|
| Web | Node.js 24 LTS, Next.js 16, React 19, TypeScript 5, Recharts, Playwright |
| API | Python 3.12+, FastAPI, Pydantic, SQLAlchemy async, Alembic |
| Storage | PostgreSQL 16, pgvector HNSW, pgcrypto, Redis 7 |
| Data and orchestration | Celery, dbt-postgres, Prefect-compatible flows, allowlisted Playwright rendering |
| NLP and ML | deterministic parsers, Sentence Transformers, XGBoost quantile regression, MLflow |
| Observability | Prometheus, Grafana, structured logs, health/readiness probes |
| Delivery | Docker Compose, GitHub Actions, GHCR, a repository-scoped self-hosted runner, and private Tailscale Serve ingress |

## Quick Start

### Prerequisites

- Docker 24+ with Docker Compose v2
- At least 8 GB RAM recommended for the complete local stack
- `uv` and Node.js 24 only when running services outside Docker

### Start the application

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

The one-shot migration and salary-data services must exit successfully before
the API and workers start. Verify readiness with:

```bash
curl --fail http://localhost:8000/health/ready
```

| Service | URL |
|---|---|
| Dashboard | <http://localhost:3000> |
| API documentation | <http://localhost:8000/docs> |
| MLflow | <http://localhost:5000> |

Load clearly labeled development data when the UI needs a local fixture:

```bash
docker compose exec api python scripts/seed_demo.py
```

Demo rows are never valid evidence for scraper, salary-model, or performance
readiness gates.

### Collect operational data

The operational salary input is disclosed compensation from permitted job
postings collected by the source adapters. It is not a dataset that an operator
must supply manually. Six provenance-pinned derivatives provide 3,208 unique
observations from VietJobs, TopCV and VietnamWorks, including a 179-record TopCV
cohort frozen for publication evaluation. They retain only source-supplied or
adapter-resolved record dates and never expand a coverage range into invented
monthly observations.

After reviewing the current source policy, enable only the approved adapters in
`.env`. For a workstation that must accumulate operational observations across
host and Docker restarts, start the stack with the collector overlay:

```bash
# Set only reviewed sources to true in .env and use a monitored contact mailbox.
# ENABLE_ITVIEC_SCRAPER=true
# ENABLE_TOPCV_SCRAPER=true
# ENABLE_VIETNAMWORKS_SCRAPER=true
# SCRAPER_CONTACT_EMAIL=bot@example.com
docker compose -f compose.yaml -f compose.collector.yaml up -d
curl --fail --request POST \
  --header "X-Admin-Key: $ADMIN_API_KEY" \
  "http://localhost:8000/api/admin/scrape/trigger?platform=topcv&pages=10"
```

The overlay applies `restart: unless-stopped` only to long-running services;
migrations and idempotent salary-data import remain one-shot prerequisites.
Use `docker compose down` when collection should stop intentionally.

TopCV is fetched with the declared bot identity first. If its public listing
requires JavaScript or returns managed challenge markup, the adapter uses an
allowlisted headless Chromium context whose browser-compatible user-agent still
contains that identity and whose `From` header contains `SCRAPER_CONTACT_EMAIL`.
Robots authorization and the shared five-second top-level page delay still run
before every render. The adapter does not use proxies or solve CAPTCHAs and
fails closed if public cards are unavailable.

Each source posting remains one salary sample even when it is scraped repeatedly.
A later payload with hidden compensation cannot erase a valid disclosed range,
and a historical TopCV row is merged with the matching live `platform_job_id`
instead of becoming a second training sample. Inactive postings remain available
only to the time-bounded salary dataset.
Inspect collection batches at `GET /api/admin/scrape/batches` and model coverage
at `GET /api/admin/ml/data-readiness`.

### Add monitoring

```bash
docker compose \
  -f compose.yaml \
  -f compose.monitoring.yaml \
  up -d
```

Prometheus is available at <http://localhost:9090> and Grafana at
<http://localhost:3001>. Replace all default credentials before using a shared
or production environment.

### Stop the stack

```bash
docker compose \
  -f compose.yaml \
  -f compose.monitoring.yaml \
  down
```

Do not add `--volumes` unless deleting local PostgreSQL, Redis, Grafana, MLflow,
and model state is intentional.

## Development

### Backend

```bash
uv sync --extra dev --extra analytics --extra ml --extra scraping
uv run playwright install --only-shell chromium
docker compose up -d db redis
uv run alembic upgrade head
uv run uvicorn api.main:app --reload
```

### Frontend

```bash
cd web
npm ci
npm run dev
```

The browser uses same-origin `/api` requests. During local development, Next.js
proxies those requests to the API configured in `web/next.config.mjs`.

## Quality Gates

Run the same primary checks enforced by CI:

```bash
uv run python scripts/audit_python_dependencies.py
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict api nlp scrapers workers ml flows scripts
uv run pytest --cov=api --cov=nlp --cov=scrapers --cov=ml --cov-fail-under=70

DBT_HOST=localhost uv run dbt source freshness \
  --project-dir analytics --profiles-dir analytics
DBT_HOST=localhost uv run dbt build \
  --project-dir analytics --profiles-dir analytics

cd web
npm audit --audit-level=high
npm run lint
npm run typecheck
npm run build
npm run test:e2e
```

CI also validates migrations, the skill benchmark, Terraform, Compose contracts,
Prometheus rules, Grafana dashboards, container builds, and the checked-in salary
evaluation evidence. Release scans every immutable image for secrets and
High/Critical vulnerabilities and retains the complete Trivy JSON as a workflow
artifact. A secret, a vulnerability with an available fix, or an unfixed finding
outside the explicit upstream `affected`/`fix_deferred` states fails release.
Unfixed vendor findings remain visible in the report and job summary; they are
not hidden with `continue-on-error` or a scanner ignore flag.

## API Overview

The OpenAPI schema is generated at `/openapi.json`; interactive documentation is
served at `/docs`.

| Scope | Representative endpoints |
|---|---|
| Jobs | `GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/similar` |
| Salary | `GET /api/salary/bands`, `GET /api/salary/benchmark/{title}`, `POST /api/salary/predict` |
| Analytics | `GET /api/analytics/skills/demand`, `GET /api/analytics/hiring/trends` |
| Authentication | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh` |
| Profile and matching | `PUT /api/profile`, `POST /api/profile/cv`, `GET /api/profile/matching-jobs` |
| Alerts | `POST /api/alerts`, `PUT /api/alerts/{id}`, `GET /api/alerts/{id}/history` |
| Operations | `/health/ready`, `/metrics`, and admin-key-protected `/api/admin/*` routes |

See [`docs/api.md`](docs/api.md) for authentication, pagination, privacy, and
rate-limit behavior.

## Salary Model Governance

The ML service fails closed. Training writes a candidate artifact, logs the run
to MLflow, and publishes `artifacts/salary/current` only when all release gates
pass. The main-branch publication job requires:

- finite market-segment-median metrics from a manifest-pinned first-seen holdout
  with at least 50 supported observations and five distinct segments;
- MAPE at or below 15%;
- an automated salary-data readiness report with sufficient monthly and segment
  coverage; and
- a 40-character source revision that identifies a real Git commit reachable
  from the evaluated repository `HEAD`.

The clean-room pool has 3,208 unique observations across six monthly periods,
1,149 canonical technical training rows, 392 rows in the latest month and eight
supported training segments. The frozen TopCV cohort contains 179 source IDs;
69 observations across six benchmark segments qualify for evaluation. MAPE is
11.88%, readiness passes, and unsupported inference requests still fall back to
observed market quantiles or the deterministic cold-start response.

Release retrains from the pinned snapshots at the release Git SHA, embeds the
verified bundle in the ML image, installs it at an immutable revision path and
fails deployment health when that exact artifact cannot load. Full methodology
and limitations are in the [`salary model card`](docs/salary_model_card.md);
machine-readable evidence is checked in at
[`docs/evidence/salary_evaluation.json`](docs/evidence/salary_evaluation.json).

## Security and Data Policy

- Source adapters are disabled by default and must pass a current access-policy
  review before collection is enabled.
- Shared controls enforce `robots.txt`, a declared research user agent,
  per-domain throttling, response caching, and fail-closed schema validation.
- The system stores public job-posting data, not candidate profiles from source
  platforms.
- User CV text is encrypted with pgcrypto AES-256, isolated with PostgreSQL RLS,
  excluded from analytics, and removable through the authenticated API.
- Passwords use Argon2id; access and refresh tokens are HttpOnly cookies; admin
  routes require a separate key.
- Production rejects placeholder secrets and exposes PostgreSQL, Redis, MLflow,
  and monitoring only on the private Compose network.
- Python and JavaScript dependencies are audited in CI; release images are
  scanned with a digest-pinned Trivy image and retain machine-readable reports.
- The web runtime uses Node.js 24 LTS, removes npm after building, runs as a
  non-root user, and upgrades Alpine packages before publication.

Historical datasets and taxonomies retain their upstream license assertions and
provenance; operational derivatives without a published dataset license are
marked `NOASSERTION`. Review [`docs/third_party.md`](docs/third_party.md) and
[`licenses/`](licenses/) before redistribution. This repository does not grant
a project-wide open-source license unless a root `LICENSE` file is added.

## Repository Layout

```text
api/          FastAPI routers, schemas, services, and security controls
analytics/    dbt sources, staging models, marts, tests, and freshness rules
flows/        Orchestration entry points
infra/        Terraform, cloud-init, Caddy, Prometheus, and Grafana config
migrations/   Append-only Alembic revisions
ml/           Salary training, evaluation, serving, embeddings, and matching
nlp/          Salary, title, experience, and skill normalization
scrapers/     Source adapters plus shared ethical collection controls
scripts/      Imports, backfills, validation, backup, and deployment tooling
tests/        Unit, integration, Playwright, and k6 coverage
web/          Next.js application
workers/      Celery schedules and background tasks
```

## Deployment

The primary production target is a single trusted workstation running Docker
and a repository-scoped GitHub Actions runner. Tailscale Serve terminates HTTPS
and proxies the dashboard from `127.0.0.1:3000`; the service is available only
to authenticated devices in the same tailnet, and no database, monitoring, or
application port is exposed to the LAN or public Internet. GitHub Actions builds
commit-addressed GHCR images and deploys immutable release directories with
health checks, private HTTPS smoke testing, and rollback.

The release pipeline retrained the revision-bound model and published all three
images for commit `12a5d99b39b9d76c9e2e976d9390485facd5cbff`. The dependent
self-hosted deployment passed Alembic migration, exact-revision model loading,
API/ML/monitoring health, private HTTPS smoke, and rollback retention. Direct
Playwright checks also passed against the live tailnet URL. The Terraform module
and manual `Deploy Hetzner` workflow remain an optional paid public-host
fallback. Follow
[`docs/operations.md`](docs/operations.md) for the complete deployment, backup,
restore, rotation, and rollback runbook.

## Documentation

- [Implementation plan](implementation_plan.md)
- [Architecture](docs/architecture.md)
- [API contracts](docs/api.md)
- [Data dictionary](docs/data_dictionary.md)
- [Operations runbook](docs/operations.md)
- [Salary model card](docs/salary_model_card.md)
- [Completion audit](docs/completion_audit.md)
- [Third-party data and attribution](docs/third_party.md)
