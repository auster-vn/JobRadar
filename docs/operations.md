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
window. The six bundled salary snapshots form a reproducible baseline with
separate provenance; they do not replace continued collection or drift review.

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

The 2026-07-18 and 2026-07-19 reviews found that the public listing paths used
by TopCV and ITViec were permitted by their current robots files. The reviewed
runtime produced these local database results:

- ITViec batch `e0fed1a8-666b-4624-94f4-817a19fb9b9f` completed with 499 jobs,
  89 inserts, 410 updates and zero errors; the database contains 630 unique
  ITViec jobs. The current source payload did not disclose salary values.
- TopCV batch `42c0cbd6-0939-4304-ba41-2bf2766aef6a` completed the original
  software-engineer route with 377 inserts and zero errors; 195 rows disclosed
  valid salary.
- The broader public IT route then completed batch
  `eb00da89-c02b-49d1-be3e-68d7a3946c50` with 465 jobs, 29 inserts, 436 updates
  and zero final errors. The database contains 690 unique TopCV jobs and 383
  disclosed salary rows across both route histories.
- The broad run exposed `Tới 0.0 triệu`. The parser now rejects nonpositive
  endpoints as undisclosed instead of violating the salary constraint;
  regression tests cover both upper-bound and zero-range forms.

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

In development, `ml-api` watches `artifacts/salary/current` through a read-only
volume. In production, release training embeds a verified seed in the ML image;
the one-shot `salary-model` service installs it under
`artifacts/salary/releases/<Git SHA>`, and `ml-api` requires that exact source
revision. Deployment health requires `model_available=true`. A bundle is served
only when status is `published`, readiness passes, MAPE is finite and at most
15%, and the requested role/level/location is supported. Other requests use the
public API fallback.

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
  artifacts/salary/current/metadata.json \
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

It accepts only a `published` artifact with no failed gates, finite
market-segment-median metrics from at least 50 supported holdout observations
across five segments, a manifest-pinned first-seen split, MAPE at or below 15%,
passing readiness and a reachable 40-character Git source revision. Keep the
evidence tied to its MLflow run; do not hand-edit metrics. A failed main-branch
publication job prevents automatic release.

Reproduce the release artifact against an empty migrated database containing
only the six pinned snapshots:

```bash
export SOURCE_REVISION="$(git rev-parse HEAD)"
export SALARY_HOLDOUT_MANIFEST=data/salary_holdout_2026-07-19.json
uv run python scripts/train_salary_release.py
```

The command exits nonzero unless the candidate publishes, its source revision
is reachable from `HEAD`, the evidence contract passes and the serialized model
can be loaded. The Release workflow performs this clean-room training again,
uploads the 1 MB-class bundle as a short-lived workflow artifact and embeds it
only in the revision-matched ML image.

The salary baseline has six compact, reviewable derivatives:

- `data/vietjobs_it_salary_observations.csv`: 1,115 rows from the MIT-licensed
  VinNLP VietJobs dataset at commit
  `ea140511b77935704e93d21c2973b72f46d48902`, SHA-256
  `f823fdb009c69ff9a2e8a367497936fcd7001adcfa60bc4dc0784d6c55ff357c`.
- `data/topcv_2026_it_salary_observations.csv`: 818 rows derived from version 1
  of the CC-BY-4.0 Kaggle dataset
  `baocgb/vietnam-it-jobs-raw-data-from-topcv-2026`, SHA-256
  `977b7da686d78e507b8424a28210d7746bfb3bb20acec1e0920cc1165de1be4e`.
- `data/topcv_canhphu_2026_salary_observations.csv`: 744 rows from seven dated
  snapshots at `canhphu/job_prediction` commit
  `5cce1ddf501ae3e8ddfce046f3b82a1990570eeb`, SHA-256
  `0d8dc1cfa6d48d96e803d55781fdc5757ef763e54b340d5e670601d6189080ee`.
- `data/topcv_operational_2026-07-18_salary_observations.csv`: 180 pre-holdout
  TopCV rows, SHA-256
  `97a09d0d8470f31436bf741e8a89d02ba268ef146ad2e8f2d0dd61a022a21575`.
- `data/vietnamworks_operational_2026-07-18_salary_observations.csv`: 172
  pre-holdout rows, SHA-256
  `d99d899d4cfbda63d9d6d03dc37263d03e5dbde071ad9a017e544d4702634478`.
- `data/topcv_2026-07-19_it_salary_observations.csv`: 179 TopCV rows frozen as
  the publication cohort, SHA-256
  `33f0ffc88415a05db9dc4e02ce18370aca84e57d2291f2320a677d1f7d37368b`.

Compose verifies every hash and imports all 3,208 rows idempotently after
migrations, then backfills experience, location, title and level for previously
collected jobs. A TopCV observation and live job with the same source ID become
one model row using the earliest observed date; re-import also retains that
earliest date. Historical observations never enter live job search results. Use
only the source-specific exporters and pinned inputs described in
`docs/third_party.md`.

Do not infer observation dates from dataset coverage ranges, application
deadlines, file modification times or repository commit dates. Admit a new
historical salary source only when its revision or collection boundary is
pinned, its license assertion is recorded (including `NOASSERTION`), and it has
a stable source-record identity, salary units, and a defensible per-record
observation or posting date. Store that evidence in `source_metadata`. A source
without those fields may be assessed offline, but it must not increase readiness
or enter publication evaluation.
`import_salary_observations` enforces non-empty source identity, a date-only
snapshot value, and non-empty `dataset`, `dataset_commit` and `license`
provenance before opening a database transaction.

The July 2026 review admitted the dated TopCV Kaggle derivative, the pinned
Canhphu archive, two pre-holdout operational derivatives and the frozen TopCV
cohort. It did not use coverage-range interpolation, application deadlines,
file modification time or repository commit time as record dates. VietJobs has
no row-level date and therefore remains one October snapshot. Sources without
stable identity, salary units or per-record dating remain excluded from
publication data even for this personal project.

Publication training requires `data/salary_holdout_2026-07-19.json`; the
manifest pins 179 first-seen TopCV source keys and its snapshot hash. Automatic
temporal or stable-hash splits remain development diagnostics and cannot pass
the evidence evaluator without a manifest hash. Training and holdout partitions
derive their segment medians independently, and sparse segments with fewer than
three records are excluded. Text/categorical vocabularies and serving support
are fitted from training only. Quantile offsets use train-only folds, while the
interval radius uses a later train-only temporal partition. Candidate artifacts
must survive a serialize/load round trip before publication.

Publication additionally requires six monthly periods, 1,000 canonical
technical training rows, at least five supported primary-city role/level
segments, 200 rows in the latest month, unique source keys and normalized VND.
A supported segment needs 30 training rows over three months; underqualified
segments remain diagnostics and are never served. Inspect
`GET /api/admin/ml/data-readiness`. The clean-room report contains 3,208 unique
rows, six periods, 1,149 canonical technical training rows, eight supported
segments, 392 latest-month rows, no duplicate keys and no non-VND rows. Readiness
is `true`.

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

### GitHub Actions release and deployment

`.github/workflows/release.yml` runs after a successful `CI` workflow on `main`
or through `workflow_dispatch`. It reconstructs and validates the salary model,
then builds backend, ML and web images and pushes immutable commit-SHA tags to
GHCR. A successful Release run triggers `.github/workflows/deploy.yml`; a failed
model or image gate cannot start deployment. Deploy may also be rerun explicitly
through `workflow_dispatch` without rebuilding an already published release.

Deploy uploads only runtime configuration and starts the target with
`--no-build`. The target stores immutable releases under
`/opt/jobradarvn/releases/<commit>` by default. Internal health checks activate
the new `current` symlink; public TLS smoke checks cover readiness, dashboard,
jobs and salary routes. A failed deployment or smoke test restores the previous
release and leaves the Deploy workflow failed. Release success is artifact
evidence only and is never treated as production-deployment evidence.

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
