# Data dictionary

PostgreSQL is the system of record. Identifiers are UUIDs and timestamps are
stored as timezone-aware values. Salary amounts are monthly VND after ingestion.

| Relation | Grain | Purpose |
| --- | --- | --- |
| `raw_jobs` | source + source job ID | Latest validated source payload and ingestion state |
| `companies` | normalized company | Canonical employer identity and metadata |
| `jobs` | source + source job ID | Searchable normalized listing |
| `job_embeddings` | job | 384-dimensional semantic vector with model provenance |
| `users` | account | Credentials and notification routing; private |
| `user_profiles` | user | Skills, preferences and pgcrypto-encrypted CV text; private |
| `salary_observations` | source record | Licensed historical salary samples; never shown as live jobs |
| `job_alerts` | alert rule | User-owned match and delivery configuration |
| `alert_events` | alert + job | Idempotent delivery status and error history |
| `scrape_batches` | source run | Started/completed time and ingestion counters |

## Important job fields

`title_normalized` and `job_level` are deterministic NLP outputs.
`skills_required` and `skills_nice_to_have` are canonical taxonomy labels.
`salary_min` and `salary_max` are nullable because undisclosed pay must not be
invented. `platform`, `platform_job_id`, `source_url` and `raw_job_id` preserve
provenance. Once a posting has disclosed a valid range, a later undisclosed
payload cannot replace it with nulls; a later valid range may replace it as a
source correction. For a stable source ID, ingestion retains the earliest
`posted_at` value so repeated relative-date parsing cannot move an observation
into a newer month. `is_active` is lifecycle state, not a deletion marker.

## Analytics models

`stg_itviec_jobs`, `stg_topcv_jobs` and `stg_vietnamworks_jobs` validate source
records. `int_unified_jobs`,
`salary_market_data` unions live disclosed salaries with licensed historical
observations while retaining source and snapshot date. A matching source and
source-record ID is represented once with live features and the earliest known
date. `int_salary_normalized`
and `int_job_skills` establish reusable grains. The marts
`mart_salary_bands`, `mart_skill_demand` and `mart_hiring_trends` power public
analytics. dbt tests enforce positive salaries and source uniqueness. Private
user and CV relations are intentionally absent from dbt sources.

## Retention and deletion

Source HTML is optional; normalized public job metadata and disclosed salary
can be retained for historical market trends after a vacancy becomes inactive.
Inactive jobs remain excluded from search results, and salary training applies
a six-month window. Deleting a user cascades profiles, alerts and alert events.
CV plaintext is never logged or stored; the ciphertext and semantic embedding
are deleted with the profile/account.
