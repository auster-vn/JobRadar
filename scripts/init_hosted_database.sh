#!/usr/bin/env bash
set -euo pipefail

# Execute once per deployment, in the API pre-deploy container only.
alembic upgrade head
python scripts/import_salary_snapshot.py \
  data/vietjobs_it_salary_observations.csv \
  data/topcv_2026_it_salary_observations.csv \
  data/topcv_canhphu_2026_salary_observations.csv \
  data/topcv_2026-07-19_it_salary_observations.csv \
  data/topcv_operational_2026-07-18_salary_observations.csv \
  data/vietnamworks_operational_2026-07-18_salary_observations.csv
python scripts/backfill_job_experience.py
python scripts/backfill_job_locations.py
python scripts/backfill_job_titles.py
