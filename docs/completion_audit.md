# Completion Audit

Audit date: 2026-07-19

This audit maps the executable acceptance criteria in
[`implementation_plan.md`](../implementation_plan.md) to measured evidence. A
feature is not considered production-complete because its source code exists;
the relevant test, release, deployment and smoke-test evidence must also exist.

## Current Verdict

The application and salary publication path pass their local quality gates and
GitHub CI. A clean database reconstructed from the six pinned snapshots produces
a published salary model with 11.66% MAPE and passing data readiness. Release
retraining and all three GHCR image builds also pass at the audited code SHA.

The project is **not yet production-complete**. The release deployment job
stopped before SSH because no production host or secrets are configured.
Hetzner provisioning, DNS/TLS, deployment and the public production smoke test
remain required. No production URL or successful deployment is claimed here.

## Acceptance Matrix

| Scope | Status | Measured evidence |
|---|---|---|
| MVP data volume | Pass | Operational PostgreSQL contains 630 unique ITViec jobs |
| Salary bands | Pass | The salary mart exposes more than the required ten normalized roles |
| API performance | Pass | Isolated `/api/jobs` k6 run sustained the 100 RPS target with 8.37 ms p95 and 0% HTTP failures |
| Backend quality | Pass | Ruff, Ruff format, strict mypy and 244 tests pass with 80.64% coverage; CI enforces at least 70% |
| Analytics | Pass | dbt source freshness passes and `dbt build` completes 32/32 nodes locally and in CI |
| Frontend | Pass | npm audit, ESLint, TypeScript, production build and three Playwright workflows pass locally and in CI |
| Data collection | Pass locally | ITViec, TopCV and VietnamWorks completed real batches; the broad TopCV route returned 465 jobs with zero final errors |
| Salary ML publication | Pass | Frozen TopCV holdout MAPE 11.66% versus a fixed 15% maximum; readiness passes locally, in CI and in release retraining |
| Infrastructure contract | Pass | Terraform format/init/validate and two tests, production Compose resolution, actionlint and monitoring validation pass |
| Release images | Pass | Backend, web and release-seeded ML images build locally and publish to GHCR at the audited SHA |
| GitHub CI | Pass | [Run 29678361931](https://github.com/auster-vn/JobRadar/actions/runs/29678361931) completed every job successfully |
| Release workflow | Partial | [Run 29678660335](https://github.com/auster-vn/JobRadar/actions/runs/29678660335) passed model and image jobs, then failed deployment input validation |
| Live production | Blocked | No host, DNS, production secrets or public endpoint exist for migration/API/browser smoke tests |

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
| MAPE | **11.66199%** | at most 15% |
| MAE | 2,430,444 VND | informational |
| R2 | -0.2684 | informational and disclosed |
| Training-median baseline MAPE | 19.27176% | informational |
| Predictions within 15% | 75.36% | informational |
| P90 absolute percentage error | 22.02% | informational |
| Median percentage bias | +8.44% | informational |
| Train-only interval coverage | 53.62% | informational |

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
not load. Clean-room run `20fafbaba37543d3ae8d800febb3154f` is bound to source
revision `435a34f3e83e92d71abddff4809c146262e1bb39`; the compact record is
[`evidence/salary_evaluation.json`](evidence/salary_evaluation.json).

The model's negative R2 and narrow six-segment holdout are not hidden by the MAPE
pass. The model is an aggregate market benchmark, not an individual compensation
predictor; full limitations are documented in
[`salary_model_card.md`](salary_model_card.md).

## Local Validation Evidence

The following checks were completed on 2026-07-19:

- Ruff lint and formatting, plus strict mypy over 102 source files;
- 244 backend/unit/integration tests with 80.64% coverage and the 70% threshold
  enforced;
- 50-example skill benchmark with precision, recall and F1 all equal to 1.0;
- dbt source freshness and 32/32 build nodes;
- npm audit with zero known vulnerabilities, frontend lint/typecheck/build and
  three Playwright workflows;
- Python environment audit with zero known vulnerabilities;
- Terraform 1.15.5 format/init/validate and two mock-provider tests;
- actionlint 1.7.12, development/collector/production Compose resolution,
  Prometheus rules and five Grafana dashboard contracts;
- backend, web and ML Docker builds; and
- seeded ML-image installation plus a serving health check with
  `model_available=true` and matching image/artifact revisions.

## Remote Delivery Evidence

GitHub CI run
[`29678361931`](https://github.com/auster-vn/JobRadar/actions/runs/29678361931)
passed backend, frontend, browser E2E, infrastructure, ML contract, ML
publication and all three container builds at
`b124dbecbced92544f820bd88a9454fe8b8b6b93`.

Dependent release run
[`29678660335`](https://github.com/auster-vn/JobRadar/actions/runs/29678660335)
reconstructed 3,208 rows, published MLflow run
`85017efab712402a930dfeea677b6902` at the same source revision with 11.6619927%
MAPE, and built/pushed backend, web and seeded ML images. The overall workflow
correctly failed before SSH with `PRODUCTION_HOST is required`. At that point:

- the GitHub `production` Environment existed but had no protection rules;
- no repository or environment Actions secrets were configured;
- no repository Actions variables were configured; and
- no local Hetzner token, production variable file, domain, host or SSH key was
  available.

This is an external provisioning blocker, not a passed release/deployment gate.

## Remaining Production Gates

1. Provision the production host with Terraform and point an owned DNS name at
   it.
2. Protect the GitHub `production` Environment and configure the required host,
   SSH and application secrets plus `PRODUCTION_URL`.
3. Rerun release for the immutable SHA and pass deployment migration, internal
   health, public API, salary-model availability and browser smoke tests.
4. Record the production URL and successful release run, then confirm a clean
   worktree with local `main` equal to `origin/main`.

Until those gates have direct evidence, JobRadar remains locally validated but
not production-complete.
