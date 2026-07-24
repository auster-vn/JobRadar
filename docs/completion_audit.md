# Completion Audit

Audit date: 2026-07-24

This audit maps the executable acceptance criteria in
[`implementation_plan.md`](../implementation_plan.md) to measured evidence. A
feature is not considered production-complete because its source code exists;
the relevant test, release, deployment and smoke-test evidence must also exist.

## Current Verdict

JobRadar is **production-complete for its documented private, single-operator
target**. Completion applies only to a Git revision for which CI, release
retraining, all three immutable image builds and security reports, self-hosted
deployment, migration, internal health, private HTTPS smoke, production browser
E2E, and backup verification all pass. A clean database reconstructed from the
six pinned snapshots produces a published salary model with 11.88% MAPE and
passing data readiness.

The live service is <https://jobradar-production.tail92479f.ts.net> and is
intentionally reachable only by authenticated devices in the owner's Tailscale
network. The public Hetzner path remains a manual, paid fallback and is not part
of this completion claim.

## Acceptance Matrix

| Scope | Status | Measured evidence |
|---|---|---|
| MVP data volume | Pass | Operational PostgreSQL contains 1,782 unique jobs: 630 ITViec, 690 TopCV and 462 VietnamWorks |
| Salary bands | Pass | The salary mart exposes more than the required ten normalized roles |
| API performance | Pass | Isolated `/api/jobs` k6 run sustained the 100 RPS target with 8.37 ms p95 and 0% HTTP failures |
| Backend quality | Pass | Ruff, Ruff format, strict mypy and 284 tests pass with 80.69% coverage; CI enforces at least 70% |
| Analytics | Pass | dbt source freshness passes and `dbt build` completes 32/32 nodes locally and in CI |
| Frontend | Pass | npm audit, ESLint, TypeScript, production build and three Playwright workflows pass locally, in CI and directly against production |
| Data collection | Pass in production | ITViec, TopCV and VietnamWorks have completed real batches; the post-deploy TopCV probe parsed and updated 48 jobs with zero errors |
| Salary ML publication | Pass | Frozen TopCV holdout MAPE 11.88% versus a fixed 15% maximum; readiness passes locally, in CI and in release retraining |
| Infrastructure contract | Pass | Terraform format/init/validate and two tests, private self-hosted Compose ingress, actionlint and monitoring validation pass; Docker/Tailscale/runner services are persistent and only web is bound to loopback |
| Dependency security | Pass | `pip-audit` plus direct OSV verification covers 210 Python distributions and the custom PyTorch wheel with zero known findings; npm audit reports zero |
| Release images | Pass | Backend, web and release-seeded ML images build locally; Trivy finds no secret or remediable High/Critical vulnerability |
| GitHub CI | Required per revision | The [CI workflow](https://github.com/auster-vn/JobRadar/actions/workflows/ci.yml) must complete every job successfully |
| Release workflow | Required per revision | The [Release workflow](https://github.com/auster-vn/JobRadar/actions/workflows/release.yml) must publish the model, images, and three security-report artifacts |
| Live production | Required per revision | The [Deploy workflow](https://github.com/auster-vn/JobRadar/actions/workflows/deploy.yml) must pass migration, internal health, private HTTPS smoke and rollback checks |

## Collection Evidence

The operational database was populated by the source adapters, not by demo
fixtures. The latest measured source inventory is:

| Source | Unique jobs | Jobs retaining disclosed salary |
|---|---:|---:|
| ITViec | 630 | 0 |
| TopCV | 690 | 383 |
| VietnamWorks | 462 | 172 |

TopCV batch `eb00da89-c02b-49d1-be3e-68d7a3946c50` traversed the broad public IT
route and completed with 465 jobs, 29 inserts, 436 updates and zero final errors.
The parser discovered the malformed public value `Tới 0.0 triệu`; it now rejects
nonpositive endpoints as undisclosed, with regression coverage for both
upper-bound and range forms. The adapter retains robots, throttling, declared
identity and fail-closed challenge handling; it does not solve CAPTCHAs or use
proxy rotation.

After production activation, TopCV batch
`4f493de4-5a15-441a-b8be-23aaaf02df45` ran through the production Celery queue.
It parsed 48 public jobs, updated all 48 idempotently, inserted no duplicates and
completed with zero errors. The public production jobs API reports all 690
retained TopCV records.

Repeated collection preserves one salary observation per source posting. A
later payload that hides salary cannot erase an earlier valid disclosure, and
linked historical/live TopCV identifiers are deduplicated before training.

## Clean Data Evidence

An empty PostgreSQL 16 plus pgvector database was migrated to the latest Alembic
revision and populated only from the committed snapshot files. All six files
were hash-verified and imported twice to exercise idempotency:

| Check | Result |
|---|---:|
| Unique salary observations | 3,208 |
| Duplicate source keys | 0 |
| Non-VND normalized rows | 0 |
| Distinct monthly periods | 6 |
| Canonical technical training rows | 1,149 |
| Rows in the latest month | 392 |
| Supported training segments | 8 |
| dbt build | 32/32 passed |

The snapshots and their exact SHA-256 digests are documented in
[`third_party.md`](third_party.md). Operational derivatives marked
`NOASSERTION` retain source URL, source identifier, first-seen batch/timestamp,
raw payload digest and cutoff metadata without asserting an upstream license.

## Salary Publication Evidence

The evaluation cohort was frozen before its labels were used for model
selection. Manifest `salary_holdout_2026-07-19.json` identifies 179 independent
TopCV source IDs first seen after the cutoff. Sixty-nine observations across six
training-supported role/level/location segments form the publication benchmark.

| Metric | Result | Contract |
|---|---:|---:|
| MAPE | **11.88030%** | at most 15% |
| MAE | 2,477,873 VND | informational |
| R2 | -0.3193 | informational and disclosed |
| Training-median baseline MAPE | 19.27176% | informational |
| Predictions within 15% | 72.46% | informational |
| P90 absolute percentage error | 23.30% | informational |
| Median percentage bias | +8.82% | informational |
| Train-only interval coverage | 50.72% | informational |

The evaluation unit is the partition-local `market_segment_median`; holdout
labels never define training targets. Serving support is derived only from raw
training rows and requires at least 30 records over at least three months for an
exact role/level/location segment. Unsupported requests fail closed to observed
market bands or the deterministic cold-start response.

Publication requires `status=published`, no failed gates, passing readiness, a
manifest-matching holdout, MAPE at or below 15%, and a reachable 40-character Git
source revision. The release workflow retrains at its checked-out SHA, validates
the serialized bundle, embeds it only into the ML image, installs it into an
immutable revision directory and makes ML health fail if that exact bundle does
not load. Clean-room run `c550b86ee30c4ba19d6889e1398f3f9a` is bound to source
revision `62e0481385caef0be4bf6c18e2fd4cb1a11a8dfa`; the compact record is
[`evidence/salary_evaluation.json`](evidence/salary_evaluation.json).

The model's negative R2 and narrow six-segment holdout are not hidden by the MAPE
pass. The model is an aggregate market benchmark, not an individual compensation
predictor; full limitations are documented in
[`salary_model_card.md`](salary_model_card.md).

TF-IDF feature limits now resolve equal-frequency terms lexically. Independent
local and GitHub release encoders produced the same canonical vocabulary digest,
`2bd8ab1a5bc3d440a6f36d662bb1f34dd6d466e9f17e10d5feb2c5be79e1fbbf`.

## Supply-chain Evidence

The 2026-07-24 dependency refresh upgraded MLflow, PyArrow, Sentence
Transformers, Transformers, PyTorch, pytest, Next.js, PostCSS, sharp, GitPython,
and the build/runtime toolchains. Python audit covers the PyPI environment with
`pip-audit` and verifies the custom CPU PyTorch wheel directly against OSV.
Frontend audit resolves the exact npm lockfile. Both report zero known
dependency vulnerabilities.

Release scans use Trivy `0.72.0` by immutable digest, retain one JSON artifact
per image for 30 days, and evaluate the report with a fail-closed repository
script:

| Local image | Secrets | Remediable High/Critical | Upstream-unfixed High/Critical |
|---|---:|---:|---:|
| Backend with Playwright | 0 | 0 | 44: 6 Critical, 38 High |
| ML runtime | 0 | 0 | 23: 4 Critical, 19 High |
| Web runtime | 0 | 0 | 0 |

The Debian findings have no vendor fixed version and are currently marked only
`affected` or `fix_deferred`; their full package/CVE records remain in the JSON
artifact and job summary. Any available fixed version, secret, unexpected
status, malformed report, or missing image digest fails release. This is an
explicit upstream-risk record, not `--ignore-unfixed`, a lower severity
threshold, or `continue-on-error`. The web runtime moved to Node.js 24 LTS,
upgrades Alpine packages and removes npm from the final non-root image.

## Local Validation Evidence

The following checks were completed on 2026-07-24:

- Ruff lint and formatting over 157 files, plus strict mypy over 105 source
  files;
- 284 backend/unit/integration tests with 80.69% coverage and the 70% threshold
  enforced;
- 50-example skill benchmark with precision, recall and F1 all equal to 1.0;
- dbt source freshness and 32/32 build nodes;
- Python environment and npm audits with zero known dependency vulnerabilities,
  plus frontend lint/typecheck/build and three Playwright workflows;
- Terraform 1.15.5 format/init/validate and two mock-provider tests;
- actionlint 1.7.12, development/collector/production Compose resolution,
  Prometheus rules and five Grafana dashboard contracts;
- backend, web and ML Docker builds plus fail-closed Trivy report evaluation;
- a clean-room MLflow 3.14 release rehearsal using a supported SQLite tracking
  backend, with `data_ready=1`, six segments, 69 holdout rows and 11.8803% MAPE;
  and
- seeded ML-image installation plus a serving health check with
  `model_available=true` and matching image/artifact revisions.

## Historical Remote Evidence

The fully completed delivery chain immediately preceding the 2026-07-24
dependency refresh remains immutable historical evidence. GitHub CI run
[`29696200498`](https://github.com/auster-vn/JobRadar/actions/runs/29696200498)
passed every job at
`6580971a4380617ce9b70ecbad51dea8adb2704f`.

Dependent Release run
[`29696560618`](https://github.com/auster-vn/JobRadar/actions/runs/29696560618)
reconstructed 3,208 rows, published MLflow run
`35275d5b88424288b344880ff49519d3` at the same source revision with
11.8803047% MAPE, `data_ready=1`, six test segments and 69 holdout rows.

Deploy run
[`29696775928`](https://github.com/auster-vn/JobRadar/actions/runs/29696775928)
then activated that exact revision on the repository-scoped
`cp-jobradar-production` runner. Alembic is at
`007_dedupe_salary_sources (head)`; migration, salary-data and salary-model
one-shot services all exited zero; ML health loaded a published artifact whose
40-character `source_revision` matches the active release; and the external
readiness, dashboard, jobs and salary routes passed HTTPS smoke through
Tailscale Serve.

For subsequent revisions, the current CI, Release and Deploy workflow results
and the active `/health/ready` source revision are the canonical evidence. A
historical successful run is never used to accept a newer SHA.

Runtime verification also established:

- the GitHub `production` Environment permits deployment only from `main`;
- Docker and Tailscale are enabled and active; the repo-scoped runner is online,
  persistent and labeled `jobradar-production`;
- only Next.js is published, at `127.0.0.1:3000`; all other services remain on
  the Compose network and every active container uses the bounded `local` log
  driver;
- Prometheus loaded six rules, Grafana loaded one Prometheus datasource and five
  dashboards, and the production Grafana credential authenticates successfully;
- a custom-format backup was created as the unprivileged host UID with mode 600
  and passed `pg_restore --list`; and
- all three Playwright workflows passed directly against the production URL,
  after which the synthetic E2E account was removed.

## Production Gate Closure

All production gates defined by the implementation plan are closed for the
documented private target. The three reviewed scraper flags are enabled,
immutable release rollback state is retained, and the live URL is recorded
above. The optional public-cloud path and high availability are outside this
single-operator deployment scope; they are not hidden prerequisites for the
accepted target.
