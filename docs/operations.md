# Operations

## Start and migrate

Run `docker compose up --build`. The one-shot `migrate` service must complete
before API and workers start. Readiness is available at `/health/ready`.

Scrapers are off by default. Enable a source only after reviewing its current
robots and access policy, then set `ENABLE_ITVIEC_SCRAPER=true` or
`ENABLE_TOPCV_SCRAPER=true` or `ENABLE_VIETNAMWORKS_SCRAPER=true`. Keep the
declared bot user-agent, set `SCRAPER_CONTACT_EMAIL` to a monitored mailbox and
retain the shared five-second domain delay. TopCV first attempts the public
listing with that declared identity. On HTTP 403 or managed challenge markup it
uses an allowlisted Playwright Chromium renderer with a browser-compatible
user-agent that retains the declared identity and a `From` contact header. The
adapter rechecks robots and throttles every top-level page, creates an isolated
browser context per page, uses no proxy or CAPTCHA solver, and raises
`SourceBlockedError` when public cards remain unavailable. LinkedIn requires its
official API token.

Firecrawl is not bundled. Its
[self-hosting guide](https://github.com/firecrawl/firecrawl/blob/main/SELF_HOST.md)
states that the advanced Fire-engine anti-bot capability is not included in the
open self-hosted stack; adding its Redis/PostgreSQL services would not improve
this source-specific path. Reassess that tradeoff only if multiple approved
sources need a shared rendering service.
VietnamWorks first verifies the robots-permitted public search page, then uses
the same first-party JSON search endpoint as that page for at most ten pages of
50 jobs. The adapter fails on response-schema drift, deduplicates stable job IDs
and discards unsupported currencies or salaries outside 1-200 million VND after
conversion.

Operational salary history grows from these scheduled scrapes; no manually
supplied dataset is required. A source posting is keyed by platform and stable
job ID, so repeated runs do not inflate row or month counts. Ingestion preserves
a previously disclosed salary when a later payload omits compensation, accepts
a later valid disclosed range as a source correction, retains the earliest
posting timestamp, and keeps inactive postings for the six-month training
window. The bundled historical snapshot is a development baseline with separate
provenance, not a substitute for running the collectors.

After changing an approved source flag in `.env`, use the collector overlay when
the local stack must resume automatically after a host or Docker restart. It
sets `restart: unless-stopped` for long-running services while leaving migration
and salary import as one-shot prerequisites. Trigger and inspect a first
VietnamWorks run with:

```bash
docker compose -f compose.yaml -f compose.collector.yaml up -d
curl --fail --request POST -H "X-Admin-Key: $ADMIN_API_KEY" \
  "http://localhost:8000/api/admin/scrape/trigger?platform=topcv&pages=10"
curl --fail -H "X-Admin-Key: $ADMIN_API_KEY" \
  http://localhost:8000/api/admin/scrape/batches
curl --fail -H "X-Admin-Key: $ADMIN_API_KEY" \
  http://localhost:8000/api/admin/ml/data-readiness
```

Run `docker compose down` to stop collection intentionally. Starting the base
Compose file without the overlay keeps the disposable development behavior.

### Live source evidence

The 2026-07-18 policy review found that the public job-listing paths used by
TopCV and ITViec were permitted by their current robots files. The reviewed
runtime then produced these local, non-redistributed database results:

- ITViec batch `e0fed1a8-666b-4624-94f4-817a19fb9b9f` completed with 499 jobs,
  89 inserts, 410 updates and zero errors; the database contains 630 unique
  ITViec jobs. The current source payload did not disclose salary values.
- TopCV batch `42c0cbd6-0939-4304-ba41-2bf2766aef6a` completed nine listing
  pages with 377 inserts and zero errors. All 377 source IDs, source URLs,
  companies, locations and raw links are valid and unique; 195 rows contain a
  parsed VND salary range and all 377 raw payloads are processed without error.

These counts prove the adapters against the source state at that time; they are
not a guarantee that a publisher will never change markup or access policy.

## Monitoring

Run `docker compose -f compose.monitoring.yaml up -d` while the API is available
on port 8000. Prometheus is at port 9090 and Grafana at port 3001. Replace the
Grafana credentials in production. Alert rules cover API availability, p95
latency and server error rate.

MLflow is part of the main Compose stack at port 5000. The dedicated CPU ML
worker logs model parameters, the recorded split strategy, evaluation metrics,
publication-gate status and candidate artifacts there. Its model and artifact
volumes persist across container recreation; MLflow is not published in the
production override.

The internal `ml-api` process watches `artifacts/salary/current` through a
read-only volume. It remains healthy when no accepted model exists, reports
`model_available=false`, and returns 503 for prediction requests. The public API
then uses its disclosed-market result or deterministic cold-start fallback. A
bundle is served only when all model files exist and `metadata.json` records a
finite MAPE at or below the publication gate with status `published`.

## Quality and capacity gates

Run backend gates with `uv run ruff check .`, `uv run mypy --strict api nlp
scrapers workers ml flows scripts`, and `uv run pytest --cov=api --cov=nlp
--cov=scrapers --cov=ml`. Run
dbt with `DBT_HOST=localhost uv run dbt build --project-dir analytics
--profiles-dir analytics`. Frontend gates are `npm audit`, `npm run lint`, `npm
run typecheck`, and `npm run build` from `web/`.

After a verified MLflow run, export its candidate metadata instead of editing
the evidence by hand:

```bash
uv run python scripts/export_salary_evaluation.py \
  /path/to/candidate/metadata.json \
  --output docs/evidence/salary_evaluation.json \
  --run-id <32-character-mlflow-run-id> \
  --source-revision <mlflow-source-revision-tag>
```

The exporter validates the metadata shape, compacts diagnostics and readiness,
records the source metadata SHA-256 and writes atomically. The main-branch ML
publication job then evaluates that checked-in evidence with:

```bash
uv run python ml/salary/evaluate.py \
  docs/evidence/salary_evaluation.json \
  --require-data-ready \
  --require-committed-revision
```

It accepts only finite individual-row metrics from a temporal holdout of at
least 50 rows, MAPE at or below 15%, passing data readiness and a 40-character
Git source revision. Keep the evidence tied to the MLflow run; do not hand-edit
metrics to make CI pass. Pull-request contract tests and image builds remain
independent, while a failed main-branch publication job prevents automatic
release.

The historical salary baseline has two compact, reviewable derivatives:

- `data/vietjobs_it_salary_observations.csv`: 1,115 rows from the MIT-licensed
  VinNLP VietJobs dataset at commit
  `ea140511b77935704e93d21c2973b72f46d48902`, SHA-256
  `f823fdb009c69ff9a2e8a367497936fcd7001adcfa60bc4dc0784d6c55ff357c`.
- `data/topcv_2026_it_salary_observations.csv`: 818 rows derived from version 1
  of the CC-BY-4.0 Kaggle dataset
  `baocgb/vietnam-it-jobs-raw-data-from-topcv-2026`, SHA-256
  `977b7da686d78e507b8424a28210d7746bfb3bb20acec1e0920cc1165de1be4e`.

Compose verifies both hashes and imports all 1,933 rows idempotently after
migrations, then backfills experience, location, title and level for previously
collected jobs. A TopCV observation and live job with the same source ID become
one model row using the earliest observed date; re-import also retains that
earliest date. Historical observations never enter live job search results. Use
`export_vietjobs_salary_snapshot.py` or `export_topcv_salary_snapshot.py` only
with the pinned upstream inputs described in `docs/third_party.md`.

Do not infer observation dates from dataset coverage ranges, application
deadlines, file modification times or repository commit dates. Admit a new
historical salary source only when its pinned revision has an explicit license,
a stable source-record identity, salary currency and units, and a per-record
observation or posting date documented by the publisher. Store that evidence in
`source_metadata`. A source without those fields may be assessed offline, but it
must not increase readiness month counts or enter a temporal evaluation split.
`import_salary_observations` enforces non-empty source identity, a date-only
snapshot value, and non-empty `dataset`, `dataset_commit` and `license`
provenance before opening a database transaction.

The July 2026 source review admitted the dated TopCV Kaggle derivative above
because version, license, stable source IDs, units and row-level dates are all
auditable. It rejected `jasong03/salary`: revision
`8257f706719e9aefadcef090efbe2ddb4a269390` publishes only `data.txt`, without a
dataset card or license metadata. VietJobs remains admissible under MIT, but its
public CSV has no date column; the publisher's July-October coverage statement
therefore cannot be expanded into per-record monthly observations. The
[215-row Kaggle snapshot](https://www.kaggle.com/datasets/nguyenchitinh/vietnam-jobs-dataset)
was also rejected: its page labels the dataset MIT while its own description
limits redistribution and does not identify the data owner. Commercial
[Techmap Vietnam feeds](https://jobdatafeeds.com/data/countries/vn) provide
additional dated history but require an owner-approved contract and schema
review before use.

Salary training uses complete observation dates for a temporal holdout only
when both sides meet the minimum sample sizes. A single-snapshot dataset falls
back to a deterministic split derived from stable source record keys and records
that strategy in MLflow. Text and categorical vocabularies are fitted on the
training partition only. Quantile offsets use three-fold out-of-fold residuals
from that same training partition and never the evaluation holdout. Training
data retains disclosed live salaries for six months and licensed historical
observations for 24 months even when the vacancy becomes inactive. When both
represent the same source ID, live features are retained with the earliest
observed date and the historical retention window; inactive vacancies remain
absent from job search.
Candidate artifacts must survive a serialize/load prediction round-trip and
pass MAPE at 15% before `artifacts/salary/current` is written.

Publication additionally requires the automated data-readiness report to pass:
six monthly periods, 1,000 canonical technical-role rows, at least 30 rows over
three months for every observed primary-city role/level segment, 200 rows in the
latest month, unique source keys and fully normalized VND amounts. Inspect the
live report at `GET /api/admin/ml/data-readiness`. Retraining persists the report
to Redis so Prometheus and the Product dashboard expose the same evidence.
The 2026-07-19 local report contains 2,285 unique rows across five months, 948
canonical technical rows, seven qualified and 126 underqualified segments among
133 candidates, and 222 latest-month rows. Duplicate-key, currency and final
month checks pass; overall readiness remains false.

With k6 installed, execute
`BASE_URL=http://localhost:8001 k6 run tests/load/jobs.js`. `BASE_URL` is
required so the test cannot silently target the public rate-limited process.
The scenario requests 100 jobs feeds per second for one minute and fails when
HTTP errors reach 1% or p95 endpoint latency reaches 500 ms. Run this against a
production-like dataset, not the 64-row demo seed.

Start a dedicated API process with `RATE_LIMIT_ENABLED=false` on an isolated
port for capacity testing. Never disable rate limiting on a public deployment.
`X-Forwarded-For` is ignored unless `TRUST_PROXY_HEADERS=true`; only enable that
setting behind a trusted reverse proxy that overwrites incoming forwarding headers.

## Production deployment and backup

Provision the host from `infra/terraform` before configuring CD. The module uses
the current CX32 replacement for the retired CX31 plan, attaches the restrictive
firewall before first boot, enables managed backups and protection, and prepares
a non-root Docker deployment account through cloud-init. Store Terraform state
in a private encrypted remote backend and export `HCLOUD_TOKEN`; never commit
tokens, state, `backend.tf` or `terraform.tfvars`. After `terraform apply`, create
DNS A/AAAA records from the outputs and wait for `/var/lib/cloud/instance/boot-finished`
on the host before enabling releases.

Set `DOMAIN`, `DB_PASSWORD`, a random `JWT_SECRET_KEY` of at least 32 characters,
and a separate `ADMIN_API_KEY` of at least 24 characters. Use URL-safe random
values without whitespace; the database password is interpolated into an asyncpg
URL. A manual server-side deployment behind Caddy is:

```bash
docker compose \
  -f compose.yaml \
  -f compose.production.yaml \
  -f compose.monitoring.yaml \
  -f compose.monitoring.production.yaml \
  up -d --build
```

Caddy obtains and renews TLS certificates. Browser API calls remain same-origin
and Next.js proxies them to the internal API service. PostgreSQL, Redis and
MLflow are not published by the production override. The production `backup`
service writes an atomic custom-format PostgreSQL dump every 24 hours to
`BACKUP_DIR` (default `/srv/jobradar-backups`) and retains 14 days. Configure
`BACKUP_INTERVAL_SECONDS` and `BACKUP_RETENTION_DAYS` when needed. Copy dumps to
off-host storage; local retention is not disaster recovery. Restore into an
empty database with `pg_restore --clean --if-exists --no-owner` after first
validating the dump on a staging instance. `scripts/backup_postgres.sh` remains
available for an immediate operator-triggered dump.

### GitHub Actions release deployment

`.github/workflows/release.yml` runs after a successful `CI` workflow on `main`
or through `workflow_dispatch`. It builds backend, ML and web images, pushes
commit-SHA tags to GHCR, uploads only runtime configuration, then deploys with
`--no-build`. The target stores immutable releases under
`/opt/jobradarvn/releases/<commit>` by default. Internal health checks activate
the new `current` symlink; public TLS smoke checks cover readiness, dashboard,
jobs and salary routes. A failed release restores the previous release.

Cloud-init configures Docker's `local` log driver with three 10 MB files per
container. Before pulling a release, the deployment script removes dangling
images and requires at least 10 GiB free under the deployment filesystem;
`MIN_FREE_DISK_MB` may raise or lower that threshold for a deliberately sized
host. After a successful public smoke test, cleanup retains the five newest
release directories plus the active and recorded rollback releases. It validates
their immutable GHCR references, removes only unreferenced JobRadar backend, ML
and web images from the same repositories, skips images used by containers and
never prunes volumes. Run the same bounded cleanup manually with:

```bash
bash /opt/jobradarvn/current/scripts/prune_production_releases.sh \
  /opt/jobradarvn 5
```

Configure a protected GitHub Environment named `production` with required
reviewers. Set `PRODUCTION_URL` and optional `DEPLOY_ROOT` environment variables,
plus these environment secrets:

- `PRODUCTION_HOST`, `PRODUCTION_USER`, `PRODUCTION_SSH_KEY` and a pinned
  `PRODUCTION_KNOWN_HOSTS` entry.
- `DOMAIN`, `DB_PASSWORD`, `JWT_SECRET_KEY`, `ADMIN_API_KEY`,
  `CV_ENCRYPTION_KEY` and `GRAFANA_ADMIN_PASSWORD`; `GRAFANA_ADMIN_USER`
  defaults to `admin`. Generate the CV key independently with at least 32
  random URL-safe characters and retain it in the secret manager: database
  backups contain ciphertext and cannot recover a lost key.
- Optional provider credentials: `LINKEDIN_ACCESS_TOKEN`, `TELEGRAM_BOT_TOKEN`,
  `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` and `SMTP_PASSWORD`.

Set `ENABLE_ITVIEC_SCRAPER`, `ENABLE_TOPCV_SCRAPER` and
`ENABLE_VIETNAMWORKS_SCRAPER` as environment variables only after reviewing
current source policy and completing a live probe. Set
`SCRAPER_CONTACT_EMAIL` as a repository variable pointing to a monitored
mailbox. The target needs Docker with
Compose and permission for the deployment user to run Docker. GHCR access uses
the workflow's short-lived token and is removed after deployment.

The release includes Prometheus and Grafana on the private Compose network.
Neither monitoring port is published in production; use an SSH tunnel for
administrative access. Prometheus scrapes `api:8000` directly, so monitoring does
not depend on a host-published API port.

To rotate CV encryption without exposing keys in shell arguments, first take a
verified database backup. Run the transactional rotation against the active
release, then replace `CV_ENCRYPTION_KEY` in the protected GitHub Environment
before the next deployment:

```bash
read -rsp 'Old CV key: ' OLD_CV_ENCRYPTION_KEY && printf '\n'
read -rsp 'New CV key: ' NEW_CV_ENCRYPTION_KEY && printf '\n'
export OLD_CV_ENCRYPTION_KEY NEW_CV_ENCRYPTION_KEY
docker compose run --rm \
  -e OLD_CV_ENCRYPTION_KEY -e NEW_CV_ENCRYPTION_KEY \
  api python scripts/rotate_cv_encryption_key.py
unset OLD_CV_ENCRYPTION_KEY NEW_CV_ENCRYPTION_KEY
```

The command decrypts and re-encrypts every populated CV in one transaction. An
incorrect old key aborts and rolls back the complete update. Restart API and ML
workers with the new `CV_ENCRYPTION_KEY` immediately after it succeeds.

To verify or roll back manually on the target:

```bash
bash /opt/jobradarvn/current/scripts/production_smoke.sh https://example.com
bash /opt/jobradarvn/current/scripts/deploy_production.sh rollback /opt/jobradarvn
```
