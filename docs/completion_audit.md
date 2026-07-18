# Completion Audit

Audit date: 2026-07-18

This document records measured acceptance evidence against
`implementation_plan.md`. A gate is only marked complete when the corresponding
runtime behavior was exercised; source files alone are not accepted as evidence.

## MVP Definition of Done

| Gate | Result | Evidence |
|---|---|---|
| At least 500 real ITViec jobs | Pass | 541 ITViec rows in the operational database |
| Salary bands for at least 10 roles | Pass | 57 bands across 41 normalized roles |
| `/api/jobs` p95 below 500 ms | Pass | Isolated k6 100 RPS target: 5,977 completed requests, p95 8.37 ms, 0% HTTP failures |
| Frontend loads below 3 seconds | Pass | `/salary` server response 5.1 ms; production build and Playwright pass |
| dbt tests pass | Pass | Freshness passed; three-source dbt build passed 32/32 |
| Unit coverage at least 60% | Pass | 188 unit/integration tests pass with 80.74% combined API/NLP/scraper/ML coverage; CI enforces at least 70% |
| Compose starts without errors | Pass | All 13 development and monitoring services started; migrations and salary import exited 0, and API, ML API, PostgreSQL and Redis health checks passed |

MVP functionality and checkpoint verification are complete. Release gates that
depend on data maturity or external production credentials remain open below.

## Roadmap Status

| Phase | Status | Runtime evidence |
|---|---|---|
| Phase 0 - Validate | Pass | 541 parsed ITViec jobs; pgvector HNSW index active; 50-example skill benchmark F1 1.00; MiniLM 384d CPU p95 14.583 ms |
| Phase 1 - Foundation | Pass | Strict Ruff/mypy, pre-commit, six Alembic revisions, Compose, Celery flow and health probes |
| Phase 2 - NLP and Data Engineering | Pass | 3,336-entry taxonomy, salary/title parsing, nine dbt models, 23 tests, freshness and scheduled Prefect/Celery orchestration |
| Phase 3 - ML Pipeline | Partial | Leakage-safe features, calibrated quantiles, gated inference service, MLflow rejection logging, 1,003 embeddings, HNSW matching and skill-gap API exist; publication MAPE gate fails |
| Phase 4 - Full Application | Pass | Latest VietnamWorks full pagination returned 414 current jobs with zero errors and retains 462 historical records; TopCV has a fail-closed paginated listing adapter; auth, alerts, encrypted CV extraction/deletion, APIs and all frontend pages pass |
| Phase 5 - Production | Partial | Validated Hetzner CX32 Terraform/cloud-init, five Grafana dashboards, Prometheus alerts, CI, immutable GHCR CD with rollback, E2E, rate limiting, docs, backup and Caddy config exist; infrastructure apply and deployment are not executed |

The original `underthesea` validation was replaced in the executable path by a
versioned skill taxonomy and deterministic extractor. Its
curated 50-description benchmark exceeds the same F1 target and is enforced by
pre-commit and CI.

## Clean Database Audit

The following sequence was run against a newly created `jobradar_clean_audit`
database:

1. Alembic upgraded an empty database through `006_retain_salary_history`, creating
   both `vector` and `pgcrypto` extensions and only the encrypted CV column. A
   separate plaintext fixture was migrated to ciphertext, verified absent from
   stored bytes, decrypted exactly, and removed after the test.
2. The test seed and 1,115-row licensed salary snapshot imported successfully.
3. The authenticated API integration workflow passed.
4. dbt source freshness passed.
5. dbt build completed with 32 passes, zero warnings and zero errors. A TopCV
   fixture traversed ingestion, staging, unified analytics and hiring trends;
   cleanup and a full refresh then restored zero fixture rows. The clean CI seed
   independently creates one ITViec, TopCV and VietnamWorks contract row, and
   `int_unified_jobs` returns exactly one row for each platform.
6. A real Celery analytics task executed freshness and build from the ML worker and returned `success`.

Frontend E2E covers salary provenance on desktop/mobile and the complete
register, CV upload, CV erase, alert create, toggle and delete workflow. The
three Playwright tests pass without page or console errors and are also wired
into GitHub Actions.

## Infrastructure and Release Audit

1. Terraform 1.15.5 initialized with the signed `hcloud` 1.66.0 provider and a
   committed dependency lock file.
2. `terraform validate` and two mock-provider infrastructure tests pass without
   contacting Hetzner or creating billable resources.
3. Cloud-init parses as valid YAML, and Ubuntu 24.04 provides the selected
   `docker-compose-v2` package.
4. Official actionlint 1.7.12 is digest-pinned in CI and validates CI/release
   workflows; development and production Compose configurations resolve exact
   image overrides correctly. Release contract tests require all three scraper
   flags to be validated and serialized into the remote environment.
5. Deployment regression tests cover immutable activation, disk preflight,
   previous-release recording, rollback, bounded release/image cleanup, public
   smoke routes and atomic restricted backups. Cleanup tests preserve active,
   rollback and container-referenced images and reject unsafe release metadata
   before deleting anything.
6. The rebuilt web container proxies `/api` same-origin; public smoke and all
   three desktop/mobile Playwright workflows pass through port 3000.
7. A real PostgreSQL backup run produced a permission-0600 custom archive with
   86 readable `pg_restore` TOC entries; production schedules the same atomic
   operation daily with retention.
8. CI validates all five Grafana dashboards for panel identity, 24-column grid
   bounds and overlap, while Prometheus 3.12.0 `promtool` validates the scrape
   configuration and all six alert rules. An enabled scraper without any
   successful batch exports `jobradar_last_successful_scrape_age_seconds=+Inf`,
   so `ScraperSilent` fires instead of silently missing the platform; disabling
   that scraper removes its series.
9. CV plaintext is encrypted with pgcrypto AES-256 under RLS. Transactional key
   rotation was exercised against a real row: the new key recovered the exact
   payload, the old key failed, and the fixture was removed.
10. Salary retention migration upgrade/downgrade was exercised with an inactive
    disclosed-salary fixture. Revision `006` and its existing dbt dependent view
    retained the row; revision `005` excluded it; re-upgrade restored it without
    dropping downstream views.
11. The release SHA is embedded in backend, ML and web images as both
    `SOURCE_REVISION` and the OCI revision label. The current ML image was rebuilt
    from `b6ae6418eb661cf19fbcff7f61b58a6995db8544`, and MLflow run
    `b4d7b96c9ed2449484411cfdf278a6ba` captured that exact committed revision
    through the production Celery path. A deployment contract test and
    actionlint protect the build-argument wiring.
12. A production-path retrain exposed a full Docker overlay filesystem. Removing
    only dangling images reclaimed 32.21 GB and restored 32 GB free. Cloud-init
    now bounds container logs at three 10 MB files, deployment requires 10 GiB
    free before pulling, and post-smoke cleanup retains five releases plus the
    active/rollback pair without touching volumes.
13. A dedicated `ml-publication` job now enforces machine-readable MLflow
    evidence on `main`. It rejects non-finite or aggregate metrics,
    non-temporal/undersized holdouts, MAPE above 15%, failed readiness and local
    source revisions. A syntactically valid SHA must also identify a real commit
    reachable from the checked-out `HEAD`; CI fetches full history for this
    provenance check. The current evidence passes provenance and intentionally
    fails only MAPE and readiness, so automatic release cannot claim the open
    Phase 3 gate.
14. GitHub Actions run
    [`29650889285`](https://github.com/auster-vn/JobRadar/actions/runs/29650889285)
    at commit `a6d2a99857d5ad039ab80340198b4fa3b884d2a8` passed backend,
    frontend, Playwright E2E, infrastructure, ML contract and all backend/web/ML
    container builds. Its overall result is correctly failed only by
    `ml-publication`; dependent release run
    [`29651126441`](https://github.com/auster-vn/JobRadar/actions/runs/29651126441)
    was skipped rather than publishing an ineligible model or deployment.
15. PostgreSQL regression coverage now scrapes the same source posting twice:
    first with a disclosed 20-30 million VND range and then with compensation
    omitted and a later posting date. Ingestion keeps the disclosed range and
    earliest `posted_at` while updating current listing metadata. The run above
    passed this case among 188 tests with 80.74% coverage and dbt 32/32.
16. On 2026-07-18 the rebuilt ingestion image completed a live ten-page
    VietnamWorks batch with 414 jobs, zero errors, zero new rows and 414 updates.
    The operational database remained at 462 unique VietnamWorks
    records and retained all 172 previously disclosed salaries after the current
    payload omitted some compensation. Worker and Celery Beat were then
    recreated with the reviewed adapter enabled; API, ML API, PostgreSQL, Redis,
    Prometheus and Grafana health checks plus all three local Playwright workflows
    passed.
17. `compose.collector.yaml` applies `restart: unless-stopped` to the nine
    long-running collection services while keeping migration and salary import
    one-shot. CI resolves and validates the merged configuration, and the live
    stack was recreated with that policy before its public-route smoke test
    passed through `http://localhost:3000`.

## Release Gates Still Open

### Salary model publication

The candidate trained on 1,287 real salary rows is deliberately rejected. Its
VietnamWorks observations were excluded from fitting and train-only selection,
forming a temporal holdout beginning 2026-06-15; the training side contains only
the October 2025 historical snapshot, exposing substantial temporal distribution
shift:

All 1,115 historical rows now re-derive title and level from raw source text on
every import instead of trusting stale derived CSV fields. Revision
`2f434fba22de3a14c1b199331c8ca18408dc72e702071bf4bbfe380daff40f58`
changed 158 stored titles and 104 levels; the same bilingual taxonomy updated
192 operational jobs and then changed zero on a second idempotency run. This
raised canonical technical coverage from 139 to 401 rows. A shared canonical
role feature improved mean MAPE from 28.83% to 28.73% across three historical
training-only folds; no temporal holdout labels informed the taxonomy or model
selection.

| Metric | Value | Gate |
|---|---:|---:|
| MAPE | 33.78% | at most 15% |
| MAE | 11,999,254 VND | informational |
| R2 | -0.1131 | informational |
| Baseline MAPE | 43.60% | training-median baseline |
| P25-P75 coverage | 36.05% | train-only OOF calibrated diagnostic |

MLflow run `b4d7b96c9ed2449484411cfdf278a6ba` is tagged `rejected` and records the
committed source revision `b6ae6418eb661cf19fbcff7f61b58a6995db8544`; no
candidate artifact is published as the current model. The internal model service
reports `model_available=false`, and the salary API safely uses observed market
quantiles with source and period provenance or its cold-start fallback while this
gate remains open. The exact compact input enforced by CI is
[`docs/evidence/salary_evaluation.json`](evidence/salary_evaluation.json).

Post-prediction diagnostics are persisted with the rejected artifact: 27.91% of
holdout predictions fall within 15% of the observed midpoint, P90 absolute
percentage error is 64.71%, median bias is -18.86%, and 69.77% of exact
normalized holdout titles are unseen in training. The location unseen rate is
only 4.65%. Corrected canonical mapping materially reduces title-vocabulary
drift, but the untouched result still exposes temporal/source distribution
shift without allowing the holdout to influence fitting or weakening the gate.

Data readiness is executable rather than documentation-only. Training,
artifact metadata and serving require the same six-condition report;
`GET /api/admin/ml/data-readiness`, four Prometheus gauges and the Product
dashboard expose its state without weakening the publication gate. The runtime
report currently records 1,287 rows across three months, 401 canonical technical
rows, two qualified and 83 underqualified segments among 85 candidates, 84 rows
in the latest month, no duplicate source keys and no non-VND rows; readiness is
therefore false.

Meeting 15% requires a larger, more consistently labeled salary history or a
revised model validated on an untouched temporal holdout. Lowering the gate or
leaking holdout data is not an acceptable completion strategy.

A robots-aware VietnamWorks probe on 2026-07-18 traversed all ten permitted
pages and returned 414 current jobs, including 152 valid disclosed salaries
dated 2026-06-18 through 2026-07-17. A development-only root-cause experiment
combined those rows with the pinned 1,115-row snapshot. Model objectives were
selected only by three-fold training-side cross-validation: the best all-role
candidate still measured 28.62% CV MAPE and 32.47% on the current-period rows;
restricting the experiment to 396 canonical technical rows still measured
28.78% current-period MAPE. The corresponding readiness report remained false
with three months, 396 canonical rows, 84 latest-month rows and only two of 84
observed role/level/city segments qualified. This rules out a small model or
scope adjustment as a credible path to 15% on the available data.

Because the June-July observations have now been inspected repeatedly during
diagnosis, they are development validation data for future work, not an
independent publication holdout. A future publication attempt must freeze a new
later period before feature or model selection and must still satisfy every
existing readiness threshold.

This is an operational collection requirement, not a request for a manually
supplied dataset. The intended path is for approved source adapters and Celery
Beat to append new source IDs to PostgreSQL every day. Repeated scrapes keep one
sample per posting, cannot manufacture additional months and cannot erase an
earlier disclosed salary when a source later hides it.

The 2026-07-18 public-source review found no admissible shortcut. The
`jasong03/salary` Hugging Face repository has no dataset card or declared
license, so its 33 MB text file was not downloaded or imported. The licensed
VietJobs CSV exposes salary and job attributes but no record-level date; its
documented July-October collection range is not evidence that can assign an
observation month to an individual row. No deadline, commit timestamp or
coverage-range interpolation was used to inflate readiness. A 215-row Kaggle
snapshot was rejected because its MIT platform label conflicts with text
restricting redistribution and the data owner is unidentified. Techmap's dated
Vietnam feed remains a commercial procurement option, not an open dataset; it
requires owner approval, contract rights and salary-schema validation.
The 606,878-row
[`tinixai/vietnamese-job-descriptions`](https://huggingface.co/datasets/tinixai/vietnamese-job-descriptions)
corpus was also excluded: it provides only a row-level year rather than a
posting month, is licensed CC-BY-NC-4.0, and its own documentation requires
source-term review before production or commercial use. It cannot establish six
monthly periods or be bundled into this product as a readiness shortcut.

### External source and production dependencies

- Version-control bootstrap is complete: private repository
  [`auster-vn/JobRadar`](https://github.com/auster-vn/JobRadar) has a synchronized
  `main`; the latest fully audited code baseline is
  `a6d2a99857d5ad039ab80340198b4fa3b884d2a8`. The CI evidence is listed above;
  release remains intentionally blocked by the salary publication job, not by
  missing repository history.
- TopCV returned one complete 46-card, seven-page Software Engineering listing
  during the 2026-07-16 audit, then resumed returning HTTP 403. Its implemented
  parser recovered salary, experience and location for all 46 observed cards;
  the scheduled adapter remains off by default, raises `SourceBlockedError` on
  access denial and does not attempt to solve Cloudflare challenges.
- LinkedIn and notification delivery require provider-issued credentials.
- A 2026-07-18 GitHub configuration audit found no `production` Environment,
  repository secrets or repository variables. No local `terraform.tfvars`,
  Terraform backend configuration or production `.env` is present either.
  A local database, worker and Celery Beat now run the approved VietnamWorks
  schedule and preserve their volumes across Docker restarts, but they are not a
  durable public production deployment. Hetzner deployment therefore requires
  an owner-approved `HCLOUD_TOKEN` and
  Terraform apply, DNS control, creation of the protected GitHub Environment and
  unique production secrets. The validated CX32 module, cloud-init, release
  workflow, immutable image tags, rollback, production Compose override, Caddy
  TLS proxy and backup procedure are ready, but no live deployment can be
  claimed without those external inputs and an executed post-deploy smoke test.

Therefore the codebase, CI contracts and release images are ready, and the MVP
is complete. The salary data/accuracy gate and external production inputs remain
required before the full Phase 0-5 roadmap can be claimed as production
complete.
