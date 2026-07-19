# Completion Audit

Audit date: 2026-07-19

This audit maps the executable acceptance criteria in
[`implementation_plan.md`](../implementation_plan.md) to measured evidence. A
feature is not considered production-complete because its source code exists;
the relevant test, release, deployment and smoke-test evidence must also exist.

## Current Verdict

The application and salary publication path pass their local quality gates and
GitHub CI. A clean database reconstructed from the six pinned snapshots produces
a published salary model with 11.88% MAPE and passing data readiness. Release
retraining and all three GHCR image builds also pass at the audited code SHA.

The project is **not yet production-complete**. The last deployment job stopped
at the former SSH-target preflight. The selected target is now this private
workstation using a repository-scoped runner and Tailscale Serve, so no paid
cloud host or public DNS is required. Docker and Tailscale still need to be
enabled, the runner registered, and the private HTTPS deployment and smoke test
completed. No production URL or successful deployment is claimed here.

## Acceptance Matrix

| Scope | Status | Measured evidence |
|---|---|---|
| MVP data volume | Pass | Operational PostgreSQL contains 630 unique ITViec jobs |
| Salary bands | Pass | The salary mart exposes more than the required ten normalized roles |
| API performance | Pass | Isolated `/api/jobs` k6 run sustained the 100 RPS target with 8.37 ms p95 and 0% HTTP failures |
| Backend quality | Pass | Ruff, Ruff format, strict mypy and 261 tests pass with 80.72% coverage; CI enforces at least 70% |
| Analytics | Pass | dbt source freshness passes and `dbt build` completes 32/32 nodes locally and in CI |
| Frontend | Pass | npm audit, ESLint, TypeScript, production build and three Playwright workflows pass locally and in CI |
| Data collection | Pass locally | ITViec, TopCV and VietnamWorks completed real batches; the broad TopCV route returned 465 jobs with zero final errors |
| Salary ML publication | Pass | Frozen TopCV holdout MAPE 11.88% versus a fixed 15% maximum; readiness passes locally, in CI and in release retraining |
| Infrastructure contract | Pass | Terraform format/init/validate and two tests, private self-hosted Compose ingress, actionlint and monitoring validation pass; the optional live firewall API authorize/revoke contract was exercised without leaking a resource |
| Release images | Pass | Backend, web and release-seeded ML images build locally and publish to GHCR at the audited SHA |
| GitHub CI | Pass | [Run 29686395582](https://github.com/auster-vn/JobRadar/actions/runs/29686395582) completed every job successfully |
| Release workflow | Pass | [Run 29686499805](https://github.com/auster-vn/JobRadar/actions/runs/29686499805) published the model and all three images successfully |
| Live production | Blocked | [Deploy 29686670649](https://github.com/auster-vn/JobRadar/actions/runs/29686670649) failed at the retired SSH-target preflight; the private self-host target is not configured yet |

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

## Local Validation Evidence

The following checks were completed on 2026-07-19:

- Ruff lint and formatting, plus strict mypy over 103 source files;
- 261 backend/unit/integration tests with 80.72% coverage and the 70% threshold
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
[`29686395582`](https://github.com/auster-vn/JobRadar/actions/runs/29686395582)
passed backend, frontend, browser E2E, infrastructure, ML contract, ML
publication and all three container builds at
`c0e859e797752cfc0959f32f5ea888e060cda0f5`.

Dependent Release run
[`29686499805`](https://github.com/auster-vn/JobRadar/actions/runs/29686499805)
reconstructed 3,208 rows, published MLflow run
`27628985c428472caad3f7ac8c675e96` at the same source revision with 11.8803047%
MAPE, and built/pushed backend, web and seeded ML images. Release completed
successfully. It triggered independent Deploy run
[`29686670649`](https://github.com/auster-vn/JobRadar/actions/runs/29686670649),
which failed before SSH with `PRODUCTION_HOST is required` under the superseded
Hetzner-only workflow.

- the GitHub `production` Environment permits deployment only from `main`;
- generated application secrets are configured in the protected Environment;
- the paid Hetzner path is retained only as a manual fallback, and its temporary
  runner-only SSH rule passed a live API contract probe without creating a host;
- the three reviewed scraper flags are enabled; and
- the private workstation has not yet started Docker or Tailscale, registered the
  `jobradar-production` runner, or established its `.ts.net` endpoint.

This is an incomplete deployment gate; the successful artifact Release is not
presented as production evidence.

## Remaining Production Gates

1. Enable Docker and Tailscale on the workstation, authorize its Tailscale node,
   configure persistent Serve ingress to `127.0.0.1:3000`, and establish at
   least 10 GiB free under Docker's data root.
2. Register a persistent repository runner with label `jobradar-production`,
   then configure its exact `DOMAIN`, `PRODUCTION_URL`, home-scoped
   `DEPLOY_ROOT`, and monitored scraper contact in the protected Environment.
3. Rerun Deploy for the immutable SHA and pass migration, internal health,
   salary-model availability, private API smoke, and essential browser E2E.
4. Record the private production URL and successful Deploy run, then confirm a
   clean worktree with local `main` equal to `origin/main`.

Until those gates have direct evidence, JobRadar remains locally validated but
not production-complete.
