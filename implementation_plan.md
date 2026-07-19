# JobRadar VN — AI-Powered Tech Job Market Intelligence Platform
## Implementation Plan v1.2 — FINAL

> **Review #1 Fixes**: Ethical scraping, Mermaid diagram, full directory structure, SQL schema, dbt SQL detail, ML feature engineering, CI/CD, security, data quality, cost estimate, risk register, MVP definition.
>
> **Review #2 Fixes**: Proper quantile regression for salary CI (không hardcode), HNSW index thay IVFFlat (có justify), Celery priority queues + cron schedule chi tiết, Alembic migration strategy, dbt docs/data lineage, CV security threat model, skill taxonomy update process, API cursor-based pagination spec, rate limiting phân biệt auth vs anonymous, loại bỏ TimescaleDB (không phù hợp với job data).

---

## 1. Project Overview & Problem Statement

### 1.1 Bài Toán

Thị trường IT Việt Nam đang tăng trưởng mạnh nhưng **thông tin lương thiếu minh bạch**:
- 78% developer VN không biết mình có đang được trả đúng không (survey ITViec 2024)
- Fresher không biết học skill gì để maximize thu nhập
- HR benchmark lương dựa trên cảm tính, không có data
- Không có tool aggregated view của toàn bộ thị trường IT job VN

### 1.2 Core Value Proposition

```
1. Salary Benchmark
   Nhập: "Senior Backend Developer, 4 năm, HCM, Python+FastAPI"
   → "Lương thị trường: 28-45M/tháng (median 36M, P25=28M, P75=45M, n=127 jobs)"

2. Market Dashboard
   → Top 10 in-demand skills tháng này với MoM% growth
   → Salary trend theo 6 tháng per role
   → Công ty nào đang hire nhiều nhất, loại hình nào trả cao hơn

3. Job Alert thông minh
   → Set: Python, FastAPI, ≥30M, Remote preferred
   → Nhận Telegram khi match ≥ 70% skill overlap

4. Skill Gap Analysis
   → Upload CV → "Để thành Senior BE trong 6 tháng: thêm Kubernetes, System Design"
```

### 1.3 Target Users

| Segment | JTBD | Core Feature |
|---------|------|-------------|
| Developer mid-level | Biết có đang undervalued không | Salary benchmark |
| Fresher | Học gì có lương cao nhất | Skill demand heatmap |
| Senior dev | Tìm remote job phù hợp | Job matching + alert |
| HR/Talent | Benchmark để offer cạnh tranh | Salary report API |
| Researcher | Nghiên cứu thị trường IT VN | Analytics API + CSV export |

---

## 2. Ethical & Legal Considerations

> [!WARNING]
> **Scraping phải được thực hiện đúng cách để tránh rủi ro pháp lý.**

| Rule | Implementation |
|------|---------------|
| Rate limiting | ≤ 1 req/5s per domain (conservative) |
| Robots.txt | Check + respect trước mỗi scrape |
| User-Agent | `JobRadarVN-Research-Bot/1.0 (+https://jobradarvn.com/bot)` |
| PII | Không lưu data cá nhân ứng viên, chỉ public job postings |
| Cache | Cache 24h per job listing, không refetch không cần thiết |
| Opt-out | Company có thể request remove data qua email |
| Official API | Ưu tiên official API trước khi scrape |

**Data Sources Priority**:
| Platform | Approach | Notes |
|----------|----------|-------|
| ITViec | Scraping (public listings) | Lớn nhất VN cho IT |
| TopCV | Scraping + Partner API | 2nd largest |
| VietnamWorks | Scraping | General jobs, IT section |
| LinkedIn | Official API v2 | Giới hạn 500 req/day |

---

## 3. Tech Stack (Pragmatic Choices)

> [!NOTE]
> **Quyết định quan trọng**: PostgreSQL 16 (KHÔNG dùng TimescaleDB). Job data không phải OHLC time-series — indexed `posted_at` column là đủ. TimescaleDB tạo complexity không cần thiết.

| Layer | Technology | Lý do |
|-------|-----------|-------|
| **Scraping** | `httpx` async + Playwright (fallback) | Playwright chỉ khi JS-render needed |
| **HTML Parsing** | BeautifulSoup4 | Đơn giản, battle-tested |
| **NLP — VN** | `underthesea` + `pyvi` | Vietnamese word segmentation |
| **NLP — Skills** | `spaCy` + custom EntityRuler | Rule-based + statistical NER |
| **NLP — Embedding** | `sentence-transformers/all-MiniLM-L6-v2` | 384d, CPU-friendly (< 50ms/doc) |
| **Task Queue** | Celery + Redis | Priority queues cho scraping/NLP/alerts |
| **Scheduler** | Celery Beat | Cron-like, integrated với Celery |
| **Database** | PostgreSQL 16 + `pgvector` extension | Job data + semantic search |
| **Migrations** | Alembic | Schema version control |
| **Data Transform** | dbt Core + `dbt-postgres` | SQL transformations, modular |
| **Data Docs** | dbt docs (built-in) | Lineage graph + data catalog |
| **Orchestration** | Prefect 2 | Python-native DAGs, free self-host |
| **ML — Salary** | XGBoost (3 models: mean + Q25 + Q75) | Proper quantile regression |
| **ML — Matching** | pgvector HNSW cosine search | In-database, no separate service |
| **Experiment Tracking** | MLflow (SQLite backend) | Lightweight, upgrade to PG later |
| **Backend** | FastAPI + asyncpg | Fully async |
| **Frontend** | Next.js 14 App Router + TypeScript | |
| **Charts** | Recharts | React-native, lightweight |
| **Auth** | JWT (access 30min + refresh 7d) + httpOnly cookie | |
| **Search** | PostgreSQL FTS + pgvector hybrid | No separate search service |
| **Cache** | Redis (TTL 1h-24h) | Hot data: salary bands, skill demand |
| **Monitoring** | Prometheus + Grafana | |
| **Container** | Docker Compose | Local dev + staging |
| **CI/CD** | GitHub Actions | |

---

## 4. System Architecture

```mermaid
flowchart TD
    subgraph SOURCES["📄 Data Sources"]
        S1[ITViec]
        S2[TopCV]
        S3[VietnamWorks]
        S4[LinkedIn API]
    end

    subgraph INGESTION["🔄 Ingestion Layer"]
        RB[robots.txt checker]
        RL[Rate Limiter\n≤1 req/5s]
        SC[httpx Scrapers\n+Playwright fallback]
        VAL[Pydantic\nValidator]
        SOURCES --> RB --> RL --> SC --> VAL
    end

    subgraph QUEUE["⚡ Celery + Redis\nPriority Queues"]
        Q_SCRAPE[Queue: scraping\npriority=1]
        Q_NLP[Queue: nlp\npriority=3]
        Q_ALERTS[Queue: alerts\npriority=7]
        Q_ML[Queue: ml\npriority=2]
        VAL --> Q_SCRAPE
    end

    subgraph STORAGE["💾 PostgreSQL 16 + pgvector"]
        RAW[(raw_jobs\nraw HTML + JSON)]
        JOBS[(jobs\nstructured + indexed)]
        VEC[(job_embeddings\nvector 384d HNSW)]
        Q_SCRAPE --> RAW --> Q_NLP
    end

    subgraph NLP["🧠 NLP Pipeline"]
        SEG[underthesea\nSegmenter]
        SKILL[spaCy EntityRuler\nSkill Extractor]
        NORM[Title Normalizer\nSalary Parser]
        EMB[Sentence-BERT\nall-MiniLM-L6-v2]
        Q_NLP --> SEG --> SKILL --> NORM --> JOBS
        JOBS --> EMB --> VEC
    end

    subgraph DE["🔧 Data Engineering\ndbt + Prefect"]
        STG[staging/\nstg_*_jobs.sql]
        INT[intermediate/\nint_unified, int_salary_norm]
        MART[marts/\nsalary_bands\nskill_demand\nhiring_trends]
        JOBS --> STG --> INT --> MART
    end

    subgraph ML["🤖 ML Layer"]
        SP[Salary Predictor\nXGBoost × 3 models\nmean + Q25 + Q75]
        JM[Job Matcher\npgvector cosine\nHNSW index]
        SG[Skill Gap\nAnalyzer]
        MLF[MLflow\nModel Registry]
        MART --> SP & SG
        VEC --> JM
        SP --> MLF
    end

    subgraph APP["🌐 Application Layer"]
        API[FastAPI\nasyncpg]
        WEB[Next.js 14\nDashboard]
        BOT[Telegram Bot\nJob Alerts]
        ML --> API
        MART --> API
        API --> WEB & BOT
        Q_ALERTS --> BOT
    end

    subgraph OBS["📊 Observability"]
        PROM[Prometheus]
        GRAF[Grafana]
        LOKI[Loki + Promtail]
        API --> PROM --> GRAF
        API --> LOKI
    end
```

---

## 5. Full Directory Structure

```
jobradarvn/
├── scrapers/                       # Data Collection
│   ├── itviec/
│   │   ├── scraper.py             # Async httpx scraper
│   │   ├── parser.py              # BeautifulSoup parser
│   │   └── models.py              # Pydantic raw models
│   ├── topcv/
│   │   ├── scraper.py
│   │   └── parser.py
│   ├── vietnamworks/
│   │   ├── scraper.py
│   │   └── parser.py
│   ├── linkedin/
│   │   └── api_client.py          # LinkedIn API v2 client
│   └── common/
│       ├── robots.py              # robots.txt parser + cache
│       ├── rate_limiter.py        # Token bucket (per domain)
│       ├── http_client.py         # httpx async client with retry
│       └── validator.py           # Pydantic input validation
│
├── nlp/                            # NLP Processing
│   ├── segmenter.py               # Vietnamese word segmentation
│   ├── skill_extractor.py         # spaCy EntityRuler
│   ├── title_normalizer.py        # "Sr FE Dev" → "Senior Frontend Developer"
│   ├── salary_parser.py           # "15-25 triệu" → {min:15M, max:25M, currency:VND}
│   ├── embedder.py                # Sentence-BERT wrapper
│   └── skills_taxonomy.json       # 500+ IT skills with aliases, categories, versions
│
├── workers/                        # Celery Tasks
│   ├── celery_app.py              # Celery config + Beat schedule + priority queues
│   ├── scrape_tasks.py            # Scraping tasks → queue: scraping
│   ├── nlp_tasks.py               # NLP processing → queue: nlp
│   ├── alert_tasks.py             # Alert delivery → queue: alerts (priority=7)
│   └── ml_tasks.py                # Model training + dbt run → queue: ml
│
├── analytics/                      # Data Engineering (dbt)
│   ├── dbt_project.yml
│   ├── profiles.yml               # dev (localhost) + prod (env vars)
│   ├── packages.yml               # dbt-utils, dbt-expectations
│   ├── sources.yml                # Source freshness definitions
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_itviec_jobs.sql
│   │   │   ├── stg_topcv_jobs.sql
│   │   │   ├── stg_vietnamworks_jobs.sql
│   │   │   └── schema.yml         # Column docs + tests
│   │   ├── intermediate/
│   │   │   ├── int_unified_jobs.sql
│   │   │   ├── int_job_skills.sql
│   │   │   ├── int_salary_normalized.sql
│   │   │   └── int_company_stats.sql
│   │   └── marts/
│   │       ├── mart_salary_bands.sql
│   │       ├── mart_skill_demand.sql
│   │       ├── mart_hiring_trends.sql
│   │       └── schema.yml         # Full column documentation
│   └── tests/
│       ├── assert_salary_positive.sql
│       └── assert_no_duplicate_jobs.sql
│
├── migrations/                     # Alembic Schema Migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_add_pgvector.py
│       └── 003_add_user_cv_embedding.py
│
├── ml/                             # Machine Learning
│   ├── features/
│   │   ├── salary_features.py
│   │   └── encoders.py
│   ├── salary/
│   │   ├── model.py               # XGBoost × 3 (mean + Q25 + Q75)
│   │   ├── train.py
│   │   └── evaluate.py
│   ├── matching/
│   │   ├── embedder.py
│   │   └── ranker.py              # pgvector HNSW query
│   ├── skill_gap/
│   │   └── analyzer.py
│   └── evaluation/
│       ├── salary_eval.py
│       └── thresholds.py          # MAPE < 15% gate
│
├── flows/                          # Prefect Orchestration
│   ├── ingestion_flow.py          # Daily scraping flow
│   ├── nlp_flow.py                # NLP processing flow
│   ├── transform_flow.py          # dbt run + test
│   └── training_flow.py           # Weekly model retrain
│
├── api/                            # FastAPI Backend
│   ├── main.py
│   ├── routers/
│   │   ├── jobs.py
│   │   ├── salary.py
│   │   ├── analytics.py
│   │   ├── alerts.py
│   │   ├── profile.py
│   │   └── admin.py
│   ├── services/
│   │   ├── salary_service.py
│   │   ├── matching_service.py
│   │   ├── analytics_service.py
│   │   └── alert_service.py
│   └── core/
│       ├── config.py              # Pydantic Settings
│       ├── database.py            # asyncpg pool + connection
│       ├── security.py            # JWT, argon2, headers
│       ├── rate_limit.py          # Sliding window, auth-aware
│       ├── pagination.py          # Cursor-based pagination utils
│       └── metrics.py             # Prometheus instruments
│
├── web/                            # Next.js 14 Frontend
│   ├── app/
│   │   ├── (public)/
│   │   │   ├── page.tsx           # Landing page
│   │   │   ├── jobs/page.tsx      # Job search
│   │   │   └── market/page.tsx    # Market dashboard
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   └── (app)/
│   │       ├── dashboard/page.tsx
│   │       ├── salary/page.tsx
│   │       ├── alerts/page.tsx
│   │       └── profile/page.tsx
│   └── components/
│       ├── JobCard.tsx
│       ├── SalaryChart.tsx
│       ├── SkillHeatmap.tsx
│       ├── HiringTrendChart.tsx
│       └── AlertManager.tsx
│
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.monitoring.yml
│   ├── prometheus/
│   │   ├── prometheus.yml
│   │   └── alerts.yml
│   └── grafana/
│       └── dashboards/
│           ├── overview.json
│           ├── scraping.json
│           └── ml_performance.json
│
├── tests/
│   ├── unit/
│   │   ├── test_salary_parser.py
│   │   ├── test_skill_extractor.py
│   │   ├── test_title_normalizer.py
│   │   └── test_salary_predictor.py
│   ├── integration/
│   │   ├── test_api_jobs.py
│   │   └── test_api_salary.py
│   └── e2e/
│       └── test_scrape_to_api.py
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── ml_eval.yml
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── data_dictionary.md        # Auto-generated from dbt + manual edits
│   └── skill_taxonomy.md
│
├── .env.example
├── alembic.ini
├── pyproject.toml
└── README.md
```

---

## 6. Database Schema

```sql
-- ============================================
-- EXTENSION
-- ============================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy name search

-- ============================================
-- RAW LAYER
-- ============================================
CREATE TABLE raw_jobs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    platform        TEXT        NOT NULL CHECK (platform IN ('itviec', 'topcv', 'vietnamworks', 'linkedin')),
    platform_job_id TEXT        NOT NULL,
    raw_html        TEXT,
    raw_json        JSONB,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed       BOOLEAN     DEFAULT FALSE,
    error           TEXT,
    UNIQUE (platform, platform_job_id)
);
CREATE INDEX raw_jobs_unprocessed_idx ON raw_jobs (processed, scraped_at)
    WHERE processed = FALSE;

-- ============================================
-- STRUCTURED LAYER
-- ============================================
CREATE TABLE companies (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    name_normalized TEXT        UNIQUE,
    industry        TEXT,
    company_size    TEXT CHECK (company_size IN ('1-10','11-50','51-200','201-500','501-1000','1000+')),
    company_type    TEXT CHECK (company_type IN ('product','outsource','startup','enterprise','agency')),
    website         TEXT,
    logo_url        TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX companies_name_trgm_idx ON companies USING gin (name_normalized gin_trgm_ops);

CREATE TABLE jobs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_job_id          UUID        REFERENCES raw_jobs(id),
    platform            TEXT        NOT NULL,
    platform_job_id     TEXT        NOT NULL,
    company_id          UUID        REFERENCES companies(id),
    title               TEXT        NOT NULL,
    title_normalized    TEXT,
    job_level           TEXT        CHECK (job_level IN ('intern','fresher','junior','mid','senior','lead','manager','director')),
    job_type            TEXT        CHECK (job_type IN ('full_time','part_time','contract','freelance','remote')),
    location            TEXT[],
    salary_min          NUMERIC(15,2)   CHECK (salary_min > 0),
    salary_max          NUMERIC(15,2)   CHECK (salary_max > 0),
    salary_negotiable   BOOLEAN     DEFAULT FALSE,
    salary_currency     TEXT        DEFAULT 'VND' CHECK (salary_currency IN ('VND','USD')),
    description_raw     TEXT,
    description_cleaned TEXT,
    skills_required     TEXT[],
    skills_nice_to_have TEXT[],
    experience_years_min INTEGER    CHECK (experience_years_min >= 0),
    experience_years_max INTEGER,
    posted_at           TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ,
    is_active           BOOLEAN     DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (platform, platform_job_id)
);
-- Query indexes
CREATE INDEX jobs_posted_at_idx ON jobs (posted_at DESC) WHERE is_active = TRUE;
CREATE INDEX jobs_level_idx ON jobs (job_level, posted_at DESC);
CREATE INDEX jobs_skills_gin ON jobs USING GIN (skills_required);
CREATE INDEX jobs_location_gin ON jobs USING GIN (location);
-- Full-text search
CREATE INDEX jobs_fts_idx ON jobs USING GIN (
    to_tsvector('english', COALESCE(title,'') || ' ' || COALESCE(description_cleaned,''))
);

-- ============================================
-- VECTOR LAYER — HNSW index (not IVFFlat)
-- Reason: HNSW = O(log n), no pre-training needed,
--   better recall for dynamic datasets, handles
--   insertions without index rebuild.
-- IVFFlat requires: choosing lists=sqrt(n),
--   offline training, poor recall on filtered queries.
-- ============================================
CREATE TABLE job_embeddings (
    job_id      UUID        PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    embedding   vector(384) NOT NULL,
    model_name  TEXT        NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX job_embeddings_hnsw_idx ON job_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
-- m=16: each node connected to 16 neighbors (good recall vs memory tradeoff)
-- ef_construction=64: search width during build (higher = better quality, slower build)

-- ============================================
-- USER LAYER
-- ============================================
CREATE TABLE users (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT        UNIQUE NOT NULL,
    password_hash   TEXT        NOT NULL,  -- argon2id via pwdlib
    telegram_id     BIGINT,
    is_active       BOOLEAN     DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE user_profiles (
    user_id             UUID        PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    current_title       TEXT,
    experience_years    INTEGER     CHECK (experience_years >= 0),
    skills              TEXT[],
    current_salary      NUMERIC(15,2),
    target_salary       NUMERIC(15,2),
    preferred_locations TEXT[],
    preferred_job_types TEXT[],
    cv_text_encrypted   BYTEA,          -- pgcrypto AES-256 ciphertext; see security section
    cv_embedding        vector(384),    -- For job matching; user-only, server-side queries
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE job_alerts (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    required_skills     TEXT[],
    min_salary          NUMERIC(15,2),
    job_levels          TEXT[],
    locations           TEXT[],
    skill_match_min_pct NUMERIC(5,2) DEFAULT 60,
    channel             TEXT        NOT NULL CHECK (channel IN ('telegram','email')),
    is_active           BOOLEAN     DEFAULT TRUE,
    last_triggered_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- AUDIT LAYER
-- ============================================
CREATE TABLE scrape_batches (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    platform        TEXT        NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    jobs_found      INTEGER     DEFAULT 0,
    jobs_new        INTEGER     DEFAULT 0,
    jobs_updated    INTEGER     DEFAULT 0,
    errors          INTEGER     DEFAULT 0,
    status          TEXT        CHECK (status IN ('running','completed','failed'))
);

-- ============================================
-- ALEMBIC MIGRATION STRATEGY
-- ============================================
-- alembic init migrations
-- alembic revision --autogenerate -m "initial_schema"   → 001_initial_schema.py
-- alembic revision --autogenerate -m "add_pgvector"     → 002_add_pgvector.py
-- alembic upgrade head     (apply all)
-- alembic downgrade -1     (rollback one)
-- NEVER edit tables in prod without a migration file.
```

---

## 7. Data Engineering Deep Dive

### 7.1 dbt Models SQL

**`stg_itviec_jobs.sql`**:
```sql
-- Standardize raw ITViec job data
WITH source AS (
    SELECT * FROM {{ source('raw', 'raw_jobs') }}
    WHERE platform = 'itviec' AND processed = TRUE
),
parsed AS (
    SELECT
        id                                          AS raw_job_id,
        raw_json->>'job_id'                         AS platform_job_id,
        'itviec'                                    AS platform,
        raw_json->>'title'                          AS title_raw,
        raw_json->>'company_name'                   AS company_name,
        -- Salary: "15 - 25 million VND" or "$1500 - $3000"
        CASE WHEN raw_json->>'salary_currency' = 'USD'
            THEN NULLIF(regexp_replace(raw_json->>'salary_min', '[^0-9]', '', 'g'), '')::NUMERIC
            ELSE NULLIF(regexp_replace(raw_json->>'salary_min', '[^0-9]', '', 'g'), '')::NUMERIC * 1_000_000
        END                                         AS salary_min,
        CASE WHEN raw_json->>'salary_currency' = 'USD'
            THEN NULLIF(regexp_replace(raw_json->>'salary_max', '[^0-9]', '', 'g'), '')::NUMERIC
            ELSE NULLIF(regexp_replace(raw_json->>'salary_max', '[^0-9]', '', 'g'), '')::NUMERIC * 1_000_000
        END                                         AS salary_max,
        COALESCE(raw_json->>'salary_currency', 'VND') AS salary_currency,
        (raw_json->>'salary_negotiable')::BOOLEAN   AS salary_negotiable,
        ARRAY(SELECT jsonb_array_elements_text(raw_json->'skills')) AS skills,
        raw_json->>'location'                       AS location_raw,
        raw_json->>'level'                          AS level_raw,
        (raw_json->>'posted_at')::TIMESTAMPTZ       AS posted_at,
        scraped_at                                  AS dbt_source_ts
    FROM source
    WHERE raw_json->>'title' IS NOT NULL
)
SELECT * FROM parsed
```

**`int_salary_normalized.sql`**:
```sql
-- Normalize all salaries to VND/month midpoint
WITH base AS (SELECT * FROM {{ ref('int_unified_jobs') }}),
normalized AS (
    SELECT
        job_id,
        CASE WHEN salary_currency = 'USD'
            THEN salary_min * 25000 ELSE salary_min
        END                                         AS salary_min_vnd,
        CASE WHEN salary_currency = 'USD'
            THEN salary_max * 25000 ELSE salary_max
        END                                         AS salary_max_vnd,
        CASE
            WHEN salary_min IS NOT NULL AND salary_max IS NOT NULL
                THEN (
                    CASE WHEN salary_currency='USD' THEN salary_min*25000 ELSE salary_min END +
                    CASE WHEN salary_currency='USD' THEN salary_max*25000 ELSE salary_max END
                ) / 2
            WHEN salary_min IS NOT NULL THEN
                CASE WHEN salary_currency='USD' THEN salary_min*25000 ELSE salary_min END
            WHEN salary_max IS NOT NULL THEN
                CASE WHEN salary_currency='USD' THEN salary_max*25000 ELSE salary_max END
            ELSE NULL
        END                                         AS salary_midpoint_vnd,
        (salary_min IS NOT NULL OR salary_max IS NOT NULL) AS salary_disclosed
    FROM base
)
SELECT * FROM normalized
```

**`mart_salary_bands.sql`**:
```sql
-- Salary statistics by role/level/location — serves the main UI
{{ config(materialized='table', post_hook="ANALYZE {{ this }}") }}

WITH enriched AS (
    SELECT
        j.title_normalized,
        j.job_level,
        UNNEST(j.location)                          AS location,
        sn.salary_midpoint_vnd,
        j.posted_at
    FROM {{ ref('int_unified_jobs') }} j
    JOIN {{ ref('int_salary_normalized') }} sn USING (job_id)
    WHERE sn.salary_disclosed = TRUE
      AND j.posted_at >= NOW() - INTERVAL '6 months'
      AND j.is_active = TRUE
      -- Sanity filter: 1M–200M VND/month
      AND sn.salary_midpoint_vnd BETWEEN 1_000_000 AND 200_000_000
),
stats AS (
    SELECT
        title_normalized,
        job_level,
        location,
        COUNT(*)                                                        AS n_jobs,
        PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY salary_midpoint_vnd) AS p10,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY salary_midpoint_vnd) AS p25,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY salary_midpoint_vnd) AS median,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY salary_midpoint_vnd) AS p75,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY salary_midpoint_vnd) AS p90,
        AVG(salary_midpoint_vnd)                                        AS mean,
        STDDEV(salary_midpoint_vnd)                                     AS stddev,
        MIN(salary_midpoint_vnd)                                        AS min_salary,
        MAX(salary_midpoint_vnd)                                        AS max_salary,
        CURRENT_TIMESTAMP                                               AS updated_at
    FROM enriched
    GROUP BY title_normalized, job_level, location
    HAVING COUNT(*) >= 5  -- Minimum statistical sample
)
SELECT * FROM stats
```

**`mart_skill_demand.sql`**:
```sql
-- Skill frequency + MoM growth trend for heatmap
{{ config(materialized='table') }}

WITH skill_counts AS (
    SELECT
        UNNEST(skills_required)             AS skill,
        DATE_TRUNC('month', posted_at)      AS month,
        COUNT(*)                            AS job_count
    FROM {{ ref('int_unified_jobs') }}
    WHERE posted_at >= NOW() - INTERVAL '12 months'
      AND is_active = TRUE
    GROUP BY skill, month
),
with_trend AS (
    SELECT
        *,
        SUM(job_count) OVER (PARTITION BY skill)    AS total_12m,
        RANK() OVER (ORDER BY SUM(job_count) OVER (PARTITION BY skill) DESC) AS demand_rank,
        LAG(job_count) OVER (PARTITION BY skill ORDER BY month) AS prev_month_count
    FROM skill_counts
)
SELECT
    skill,
    month,
    job_count,
    total_12m,
    demand_rank,
    ROUND(
        (job_count - prev_month_count)::NUMERIC / NULLIF(prev_month_count, 0) * 100, 2
    )                                               AS mom_growth_pct
FROM with_trend
WHERE total_12m >= 10
ORDER BY total_12m DESC, month DESC
```

### 7.2 Data Lineage & Documentation

```bash
# Generate + serve dbt docs (data catalog + lineage graph)
cd analytics && dbt docs generate && dbt docs serve --port 8001
# → localhost:8001 shows: lineage graph raw_jobs → stg_ → int_ → mart_
# → Column descriptions, test coverage, source freshness
```

```yaml
# analytics/models/marts/schema.yml (excerpt)
models:
  - name: mart_salary_bands
    description: |
      Monthly salary statistics by job title, level, and location.
      Updated daily at 04:30 UTC. Source: last 6 months of jobs with disclosed salary.
      Minimum 5 data points required per band (HAVING n_jobs >= 5).
    columns:
      - name: title_normalized
        description: Canonical job title (e.g. "Senior Backend Developer")
      - name: median
        description: Median monthly salary in VND
      - name: p25
        description: 25th percentile — lower bound of "fair" salary range
      - name: p75
        description: 75th percentile — upper bound of "fair" salary range
      - name: n_jobs
        description: Number of job postings used in this band calculation
      - name: updated_at
        description: Timestamp when this mart was last materialized
```

### 7.3 Skill Taxonomy Update Process

```
nlp/skills_taxonomy.json — 500+ IT skills

Format per entry:
{
  "name": "FastAPI",
  "category": "Framework",
  "language": "Python",
  "aliases": ["fastapi", "fast-api"],
  "added": "2024-01",
  "related": ["Pydantic", "Starlette", "Uvicorn"]
}

Update cadence: Monthly
Process:
  1. Run: SELECT skill, COUNT(*) FROM jobs, UNNEST(skills_required) AS skill
          WHERE skill NOT IN (SELECT name FROM taxonomy_view)
          GROUP BY skill ORDER BY count DESC LIMIT 50
  2. Manual review by maintainer (~30 min)
  3. Add entries to taxonomy JSON
  4. Run dbt: mart_skill_demand recomputes automatically
  5. Queue Celery task to re-embed affected jobs

CI gate: JSON schema validation runs on every PR touching skills_taxonomy.json
```

---

## 8. NLP Pipeline

### 8.1 Salary Parser

```python
# nlp/salary_parser.py
import re
from dataclasses import dataclass

@dataclass
class SalaryRange:
    min_vnd: float | None
    max_vnd: float | None
    negotiable: bool
    currency: str = "VND"

USD_TO_VND = 25_000

def parse_salary(text: str) -> SalaryRange:
    """
    Handles Vietnamese salary formats:
    - "15 - 25 triệu"          → {min:15M, max:25M, VND}
    - "Lên đến 30tr"            → {min:None, max:30M, VND}
    - "$2,000 - $3,000"        → {min:50M, max:75M, VND} (converted)
    - "Thương lượng / Negotiable" → {negotiable:True}
    """
    t = text.lower().strip()

    if any(kw in t for kw in ['thương lượng', 'thoả thuận', 'negotiable', 'competitive']):
        return SalaryRange(None, None, negotiable=True)

    # USD range: $1500 - $3000
    m = re.search(r'\$\s*(\d[\d,]*)\s*[-–]\s*\$\s*(\d[\d,]*)', t)
    if m:
        lo = float(m.group(1).replace(',', '')) * USD_TO_VND
        hi = float(m.group(2).replace(',', '')) * USD_TO_VND
        return SalaryRange(lo, hi, negotiable=False, currency='USD')

    # VND million range: "15 - 25 triệu" or "15tr-25tr"
    m = re.search(r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*(triệu|tr\b|million)', t)
    if m:
        return SalaryRange(
            float(m.group(1)) * 1_000_000,
            float(m.group(2)) * 1_000_000,
            negotiable=False
        )

    # "Lên đến 30tr" / "Up to 30M"
    m = re.search(r'(?:lên đến|up to|upto|tối đa)\s*(\d+\.?\d*)\s*(triệu|tr\b|m\b)', t)
    if m:
        return SalaryRange(None, float(m.group(1)) * 1_000_000, negotiable=False)

    return SalaryRange(None, None, negotiable=True)
```

### 8.2 Skill Extractor

```python
# nlp/skill_extractor.py
import json
import spacy
from pathlib import Path

TAXONOMY = json.loads(Path("nlp/skills_taxonomy.json").read_text())

def build_nlp_pipeline():
    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler", config={"overwrite_ents": True})

    patterns = []
    for skill in TAXONOMY:
        # Exact name match
        patterns.append({"label": "SKILL", "pattern": skill["name"]})
        # Alias matches
        for alias in skill.get("aliases", []):
            patterns.append({"label": "SKILL", "pattern": alias})

    ruler.add_patterns(patterns)
    return nlp

def extract_skills(text: str, nlp) -> tuple[list[str], list[str]]:
    """Returns (required_skills, nice_to_have_skills)."""
    doc = nlp(text)
    all_skills = list({ent.text for ent in doc.ents if ent.label_ == "SKILL"})

    # Heuristic: skills near "nice to have", "plus", "bonus" → nice_to_have
    nice_to_have_skills = []
    required_skills = []
    for skill in all_skills:
        idx = text.lower().find(skill.lower())
        context = text[max(0, idx-100):idx].lower()
        if any(kw in context for kw in ['nice to have', 'plus', 'bonus', 'preferred', 'advantage']):
            nice_to_have_skills.append(skill)
        else:
            required_skills.append(skill)

    return required_skills, nice_to_have_skills
```

### 8.3 Title Normalizer

```python
# nlp/title_normalizer.py
import re

TITLE_PATTERNS = [
    # Frontend
    (r"(sr\.?|senior)\s+(fe|front.?end)\b",        "Senior Frontend Developer"),
    (r"(jr\.?|junior)\s+(fe|front.?end)\b",         "Junior Frontend Developer"),
    (r"front.?end\s+(dev|developer|engineer)",       "Frontend Developer"),
    (r"react\.?js?\s+(dev|developer)",              "Frontend Developer (React)"),
    (r"vue\.?js?\s+(dev|developer)",                "Frontend Developer (Vue)"),
    # Backend
    (r"(sr\.?|senior)\s+(be|back.?end)\b",          "Senior Backend Developer"),
    (r"(jr\.?|junior)\s+(be|back.?end)\b",           "Junior Backend Developer"),
    (r"back.?end\s+(dev|developer|engineer)",        "Backend Developer"),
    # Fullstack
    (r"full.?stack\s+(dev|developer|engineer)",      "Fullstack Developer"),
    # Mobile
    (r"(ios|android)\s+(dev|developer|engineer)",   "Mobile Developer"),
    (r"react.?native\s+(dev|developer)",             "Mobile Developer (React Native)"),
    (r"flutter\s+(dev|developer)",                  "Mobile Developer (Flutter)"),
    # Data
    (r"data\s+engineer",                            "Data Engineer"),
    (r"data\s+scientist",                           "Data Scientist"),
    (r"data\s+analyst",                             "Data Analyst"),
    (r"(ml|machine\s+learning)\s+engineer",         "ML Engineer"),
    (r"ai\s+engineer",                              "AI Engineer"),
    # DevOps
    (r"devops\s+engineer",                          "DevOps Engineer"),
    (r"(site\s+reliability|sre)\s+engineer",        "SRE"),
    # QA
    (r"(qa|quality\s+assurance)\s+(engineer|tester)", "QA Engineer"),
]

def normalize_title(title: str) -> str:
    t = title.lower().strip()
    for pattern, canonical in TITLE_PATTERNS:
        if re.search(pattern, t):
            return canonical
    return title.strip()
```

---

## 9. ML Pipeline

### 9.1 Salary Predictor — Proper Quantile Regression

```python
# ml/salary/model.py
import xgboost as xgb
import numpy as np
import pandas as pd

TOP_100_SKILLS = [...]  # Top 100 from mart_skill_demand

class SalaryPredictor:
    """
    Three separate XGBoost models for proper confidence intervals:
    - model_mean:  objective='reg:squarederror'   → point estimate
    - model_q25:   objective='reg:quantileerror', quantile_alpha=0.25 → P25
    - model_q75:   objective='reg:quantileerror', quantile_alpha=0.75 → P75

    All models trained on log1p(salary_midpoint_vnd) for stability.
    This avoids the common mistake of hardcoding CI as ±15% of estimate.
    """

    BASE_PARAMS = dict(
        n_estimators=400,
        learning_rate=0.04,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.7,
        min_child_weight=5,
        random_state=42,
    )

    def __init__(self):
        self.model_mean = xgb.XGBRegressor(
            objective='reg:squarederror', **self.BASE_PARAMS
        )
        self.model_q25 = xgb.XGBRegressor(
            objective='reg:quantileerror', quantile_alpha=0.25, **self.BASE_PARAMS
        )
        self.model_q75 = xgb.XGBRegressor(
            objective='reg:quantileerror', quantile_alpha=0.75, **self.BASE_PARAMS
        )

    @property
    def features(self) -> list[str]:
        return [
            # Ordinal
            'job_level_enc',        # intern=0 … director=7
            'company_size_enc',     # 0–5
            'experience_years_mid', # midpoint of min/max
            # Boolean flags
            'location_hcm',
            'location_hn',
            'location_remote',
            'company_type_product', # product company = 1
            'salary_disclosed',     # whether salary was public
            # Skill one-hot (top 100)
            *[f'skill_{s}' for s in TOP_100_SKILLS],
        ]

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        y_log = np.log1p(y)
        self.model_mean.fit(X[self.features], y_log)
        self.model_q25.fit(X[self.features], y_log)
        self.model_q75.fit(X[self.features], y_log)

    def predict(self, X: pd.DataFrame) -> dict:
        X_feat = X[self.features]
        return {
            "salary_estimate": int(np.expm1(self.model_mean.predict(X_feat)[0])),
            "salary_p25":      int(np.expm1(self.model_q25.predict(X_feat)[0])),
            "salary_p75":      int(np.expm1(self.model_q75.predict(X_feat)[0])),
            "currency": "VND",
        }
```

### 9.2 Job Matching (pgvector HNSW)

```python
# ml/matching/ranker.py
async def match_jobs_for_user(
    user_id: str,
    db: asyncpg.Connection,
    limit: int = 20,
    min_skill_match_pct: float = 0.5,
) -> list[dict]:
    """
    Two-stage matching:
    1. pgvector HNSW cosine similarity (semantic match from CV embedding)
    2. Re-rank by skill overlap percentage
    HNSW gives O(log n) query, no offline training required.
    """
    rows = await db.fetch("""
        WITH user_data AS (
            SELECT skills, cv_embedding FROM user_profiles WHERE user_id = $1
        ),
        semantic_matches AS (
            -- Stage 1: HNSW approximate nearest neighbor
            SELECT
                j.id,
                j.title_normalized,
                j.skills_required,
                j.salary_min,
                j.salary_max,
                j.location,
                c.name AS company_name,
                1 - (je.embedding <=> ud.cv_embedding) AS semantic_score
            FROM user_data ud, job_embeddings je
            JOIN jobs j ON j.id = je.job_id
            JOIN companies c ON c.id = j.company_id
            WHERE j.is_active = TRUE
              AND j.posted_at >= NOW() - INTERVAL '30 days'
            ORDER BY je.embedding <=> ud.cv_embedding
            LIMIT 200  -- Over-fetch for re-ranking
        ),
        with_skill_match AS (
            -- Stage 2: compute skill overlap
            SELECT
                sm.*,
                ud.skills AS user_skills,
                COALESCE(
                    ARRAY_LENGTH(
                        ARRAY(
                            SELECT UNNEST(sm.skills_required)
                            INTERSECT
                            SELECT UNNEST(ud.skills)
                        ), 1
                    )::NUMERIC / NULLIF(ARRAY_LENGTH(sm.skills_required, 1), 0),
                    0
                ) AS skill_match_pct
            FROM semantic_matches sm, user_data ud
        )
        SELECT *,
            -- Combined score: 60% semantic + 40% skill match
            0.6 * semantic_score + 0.4 * skill_match_pct AS combined_score
        FROM with_skill_match
        WHERE skill_match_pct >= $2
        ORDER BY combined_score DESC
        LIMIT $3
    """, user_id, min_skill_match_pct, limit)
    return [dict(r) for r in rows]
```

### 9.3 MLflow Experiment Tracking

```python
# ml/salary/train.py
with mlflow.start_run(run_name=f"salary_xgb_{date.today()}") as run:
    mlflow.log_params({
        "n_estimators":      BASE_PARAMS["n_estimators"],
        "max_depth":         BASE_PARAMS["max_depth"],
        "learning_rate":     BASE_PARAMS["learning_rate"],
        "n_training_jobs":   len(X_train),
        "n_features":        len(predictor.features),
        "salary_disclosed_pct": salary_disclosed_pct,
        "date_range":        f"{train_from} to {train_to}",
    })
    predictor.fit(X_train, y_train)
    metrics = evaluate(predictor, X_test, y_test)
    mlflow.log_metrics({
        "test_mae":  metrics["mae"],
        "test_mape": metrics["mape"],
        "test_rmse": metrics["rmse"],
        "r2":        metrics["r2"],
    })
    mlflow.xgboost.log_model(predictor.model_mean, "salary_mean")
    mlflow.xgboost.log_model(predictor.model_q25, "salary_q25")
    mlflow.xgboost.log_model(predictor.model_q75, "salary_q75")

    # Auto-promote if better than Production
    current_prod_mape = get_production_model_mape()
    if metrics["mape"] < current_prod_mape:
        for artifact_name in ["salary_mean", "salary_q25", "salary_q75"]:
            mlflow.register_model(
                f"runs:/{run.info.run_id}/{artifact_name}",
                f"jobradarvn-{artifact_name}"
            )
```

---

## 10. API Design

### 10.1 Endpoint List

```
# Meta
GET  /health
GET  /health/ready
GET  /version
GET  /metrics          # Prometheus scrape

# Auth
POST /api/auth/register
POST /api/auth/login    # Returns access + refresh token
POST /api/auth/logout
POST /api/auth/refresh
GET  /api/auth/me

# Jobs (cursor-based pagination, see 10.2)
GET  /api/jobs                             # Search + filter + paginate
GET  /api/jobs/{id}                        # Job detail
GET  /api/jobs/{id}/similar                # Semantic similar jobs
GET  /api/jobs/trending                    # Top jobs this week

# Salary
POST /api/salary/predict                   # Predict from profile features
GET  /api/salary/bands?title=&level=&location=
GET  /api/salary/benchmark/{title}

# Analytics
GET  /api/analytics/skills/demand          # Skill heatmap
GET  /api/analytics/skills/trending        # MoM growth
GET  /api/analytics/hiring/trends          # Company hiring velocity
GET  /api/analytics/market/overview        # Market summary
GET  /api/analytics/salary/by-skill        # Salary premium by skill
GET  /api/analytics/salary/by-company-type # Product vs outsource

# User Profile & Matching (requires auth)
GET  /api/profile
PUT  /api/profile
POST /api/profile/cv                       # Upload CV, extract skills + embedding
GET  /api/profile/matching-jobs            # pgvector matching
GET  /api/profile/skill-gap?target_title=&target_level=

# Alerts (requires auth)
POST   /api/alerts
GET    /api/alerts
PUT    /api/alerts/{id}
DELETE /api/alerts/{id}
GET    /api/alerts/{id}/history

# Admin
POST /api/admin/scrape/trigger?platform=
GET  /api/admin/pipeline/status
GET  /api/admin/scrape/batches
POST /api/admin/ml/retrain
```

### 10.2 Cursor-Based Pagination

> Offset pagination (`LIMIT N OFFSET K`) degrades at large offsets — O(offset) scan. Cursor-based is O(1).

```
Request:
  GET /api/jobs?limit=20&cursor=eyJwb3N0ZWRfYXQiOiIyMDI2LTA3LTEzVDEwOjAwOjAwWiIsImlkIjoiYWJjLTEyMyJ9

Response:
{
  "data": [ { "id": "...", "title": "...", ... }, ... ],
  "pagination": {
    "limit": 20,
    "next_cursor": "eyJwb3N0ZWRfYXQiOiIyMDI2LTA3LTEyVDEwOjAwOjAwWiIsImlkIjoieHl6LTQ1NiJ9",
    "has_more": true,
    "total_count": 4521   // Approximate via EXPLAIN estimate
  }
}

// Cursor = base64(json({"posted_at": last_item.posted_at, "id": last_item.id}))
// SQL: WHERE (posted_at, id) < ($cursor_posted_at, $cursor_id)
//      ORDER BY posted_at DESC, id DESC
//      LIMIT $limit + 1  -- fetch +1 to determine has_more
```

---

## 11. Security

```python
# api/core/security.py

# JWT
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Security Headers (middleware, all responses)
SECURITY_HEADERS = {
    "X-Content-Type-Options":   "nosniff",
    "X-Frame-Options":          "DENY",
    "Referrer-Policy":          "strict-origin-when-cross-origin",
    "Content-Security-Policy":  "default-src 'self'; img-src 'self' https: data:",
    "Permissions-Policy":       "camera=(), microphone=(), geolocation=()",
}

# Rate Limits — differentiated by auth state
# Unauthenticated (per IP):
RATE_LIMITS_ANON = {
    "POST:/api/auth/login":          "5/minute",    # Brute force protection
    "POST:/api/auth/register":       "3/minute",
    "GET:/api/jobs":                 "30/minute",   # Lower for anonymous
    "POST:/api/salary/predict":      "5/minute",
}
# Authenticated (per user_id from JWT):
RATE_LIMITS_AUTH = {
    "GET:/api/jobs":                 "120/minute",  # Higher for registered users
    "POST:/api/salary/predict":      "30/minute",
    "POST:/api/profile/cv":          "5/hour",      # CV upload expensive
    "GET:/api/profile/matching-jobs": "20/minute",
}

# Passwords: argon2id via pwdlib (memory-hard, side-channel resistant)
# Admin endpoints: X-Admin-Key header required (separate secret, rotated monthly)
```

### 11.1 CV Security Threat Model

```
Threat: CV contains PII (name, address, phone number)
Controls:
  - cv_text_encrypted stored in user_profiles, not in analytics tables
  - Row-level accessible: only the owning user_id can query their row
  - PostgreSQL RLS: POLICY "user_own_profile" USING (user_id = current_setting('app.user_id')::UUID)
  - NOT included in dbt models or analytics
  - Deleted on account deletion (CASCADE)
  - pgcrypto AES-256 encryption at rest; key supplied independently from the database
  - Transactional key-rotation utility; failed decrypt rolls back every row

Threat: CV embedding (vector) leaks semantic information
Controls:
  - cv_embedding is personal data, never shared cross-user
  - Matching queries executed server-side; only ranked results (job IDs) returned
  - Users can DELETE their cv_embedding via PUT /api/profile with cv_embedding=null
  - Embedding not stored in logs

Threat: CV upload used to inject malicious content
Controls:
  - Only .pdf, .docx, .txt accepted (MIME type check + magic bytes)
  - Max file size: 5MB
  - Text extraction in isolated subprocess (no exec of uploaded content)
  - Strip all metadata from extracted text
```

---

## 12. Data Quality Gates

### 12.1 Scraper Validation (Pydantic)

```python
# scrapers/common/validator.py
class RawJobValidator(BaseModel):
    platform: Literal['itviec', 'topcv', 'vietnamworks', 'linkedin']
    platform_job_id: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=3, max_length=300)
    company_name: str = Field(..., min_length=1)
    description: str | None = Field(None, min_length=20)
    posted_at: datetime
    scraped_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode='after')
    def posted_at_not_future(self) -> 'RawJobValidator':
        if self.posted_at > datetime.utcnow() + timedelta(hours=1):
            raise ValueError(f"posted_at {self.posted_at} is in the future")
        return self
```

### 12.2 dbt Tests

```yaml
# analytics/models/staging/schema.yml
models:
  - name: stg_itviec_jobs
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [platform, platform_job_id]
    columns:
      - name: title_raw
        tests: [not_null]
      - name: salary_min
        tests:
          - dbt_expectations.expect_column_values_to_be_between:
              min_value: 1000000        # 1M VND minimum
              max_value: 500000000      # 500M VND max
              mostly: 0.99             # Allow 1% edge cases
      - name: posted_at
        tests:
          - dbt_expectations.expect_column_values_to_be_between:
              min_value: "'2020-01-01'::date"
              max_value: "CURRENT_DATE + INTERVAL '1 day'"

sources:
  - name: raw
    tables:
      - name: raw_jobs
        freshness:
          warn_after: {count: 25, period: hour}
          error_after: {count: 48, period: hour}
        loaded_at_field: scraped_at
```

---

## 13. Celery Configuration (Priority Queues + Beat Schedule)

```python
# workers/celery_app.py
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

app = Celery('jobradarvn', broker=REDIS_URL, backend=REDIS_URL)

# ── Priority Queues ──────────────────────────────────────────────────────────
# Redis priority: 0-9 (higher number = higher priority)
app.conf.task_routes = {
    'workers.scrape_tasks.*': {'queue': 'scraping', 'priority': 2},
    'workers.nlp_tasks.*':    {'queue': 'nlp',      'priority': 4},
    'workers.alert_tasks.*':  {'queue': 'alerts',   'priority': 8},  # Urgent!
    'workers.ml_tasks.*':     {'queue': 'ml',       'priority': 1},  # Lowest: training
}
app.conf.task_queues = (
    Queue('scraping', priority=2),
    Queue('nlp',      priority=4),
    Queue('alerts',   priority=8),
    Queue('ml',       priority=1),
)

# ── Beat Schedule ────────────────────────────────────────────────────────────
app.conf.beat_schedule = {
    'scrape-itviec':    {'task': 'workers.scrape_tasks.scrape_itviec',
                         'schedule': crontab(hour=2, minute=0)},       # 2:00 AM daily
    'scrape-topcv':     {'task': 'workers.scrape_tasks.scrape_topcv',
                         'schedule': crontab(hour=3, minute=0)},       # 3:00 AM daily
    'scrape-vnworks':   {'task': 'workers.scrape_tasks.scrape_vnworks',
                         'schedule': crontab(hour=3, minute=30)},      # 3:30 AM daily
    'run-dbt':          {'task': 'workers.ml_tasks.run_dbt_transform',
                         'schedule': crontab(hour=4, minute=30)},      # After scraping
    'check-alerts':     {'task': 'workers.alert_tasks.check_and_fire',
                         'schedule': crontab(minute='*/30')},           # Every 30 min
    'mark-expired-jobs':{'task': 'workers.scrape_tasks.mark_expired_jobs',
                         'schedule': crontab(hour=6, minute=0)},       # 6:00 AM daily
    'retrain-salary':   {'task': 'workers.ml_tasks.retrain_salary_model',
                         'schedule': crontab(day_of_week=0, hour=5)},  # Sunday 5:00 AM
}
```

---

## 14. Observability

### 14.1 Prometheus Metrics

```python
# api/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Scraping
scrape_total        = Counter('jrvn_scrape_total', 'Scrape requests', ['platform', 'status'])
scrape_duration     = Histogram('jrvn_scrape_duration_seconds', 'Scrape time', ['platform'])
jobs_ingested_total = Counter('jrvn_jobs_ingested_total', 'Jobs ingested', ['platform'])

# NLP
nlp_duration        = Histogram('jrvn_nlp_duration_seconds', 'NLP processing per doc')
skills_extracted    = Histogram('jrvn_skills_extracted_count', 'Skills per job',
                                buckets=[0, 1, 3, 5, 8, 12, 20])

# ML
salary_pred_latency = Histogram('jrvn_salary_pred_duration_seconds', 'Prediction latency',
                                buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0])
salary_model_mape   = Gauge('jrvn_model_mape', 'Current salary model MAPE')
matching_latency    = Histogram('jrvn_matching_duration_seconds', 'pgvector query time')

# Business
active_alerts_total = Gauge('jrvn_active_alerts_total', 'Active job alerts')
alerts_fired_total  = Counter('jrvn_alerts_fired_total', 'Alerts fired', ['channel'])
jobs_indexed_total  = Gauge('jrvn_jobs_indexed', 'Total active jobs in DB')
```

### 14.2 Grafana Dashboards

| Dashboard | Key Panels |
|-----------|-----------|
| 🔄 Scraping | jobs/hour per platform, success rate, error log |
| 🔧 Pipeline | NLP queue depth, dbt run success/fail, freshness |
| 🤖 ML | MAPE trend, prediction latency P50/P95, weekly retraining result |
| 🌐 API | Request rate, P50/P95/P99, error rate by endpoint |
| 📊 Business | Total jobs indexed, DAU, alerts sent, top searched skills |

### 14.3 Alert Rules

```yaml
# infra/prometheus/alerts.yml
groups:
  - name: jobradarvn
    rules:
      - alert: ScraperSilent
        expr: rate(jrvn_jobs_ingested_total[1h]) == 0
        for: 3h
        labels: { severity: warning }
        annotations:
          summary: "No new jobs ingested for 3 hours"

      - alert: SalaryModelDrift
        expr: jrvn_model_mape > 0.20
        for: 1h
        labels: { severity: warning }
        annotations:
          summary: "Salary model MAPE {{ $value }} exceeds 20% — retrain needed"

      - alert: NLPQueueBacklog
        expr: celery_queue_length{queue="nlp"} > 500
        for: 30m
        labels: { severity: warning }
        annotations:
          summary: "NLP queue > 500 jobs — workers may be down"
```

---

## 15. CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install ruff mypy
      - run: ruff check .
      - run: mypy api/ ml/ scrapers/ nlp/ --ignore-missing-imports

  test-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements-dev.txt
      - run: pytest tests/unit/ -v --tb=short -x --cov=. --cov-fail-under=65

  test-integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_DB: jobradarvn_test
          POSTGRES_PASSWORD: testpass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements-dev.txt
      - env:
          DATABASE_URL: postgresql://postgres:testpass@localhost/jobradarvn_test
          REDIS_URL: redis://localhost:6379
        run: |
          alembic upgrade head
          pytest tests/integration/ -v --cov=api --cov-fail-under=70

  dbt-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env: { POSTGRES_DB: dbt_test, POSTGRES_PASSWORD: testpass }
    steps:
      - uses: actions/checkout@v4
      - run: pip install dbt-postgres dbt-utils dbt-expectations
      - working-directory: analytics
        run: |
          dbt deps
          dbt compile --profiles-dir .
          dbt run --profiles-dir .
          dbt test --profiles-dir .

  ml-evaluation:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - run: |
          pip install xgboost scikit-learn pandas
          python ml/salary/evaluate.py \
            --holdout-days 30 \
            --output ml/results/metrics.json
      - name: Enforce MAPE < 15%
        run: |
          python -c "
          import json, sys
          m = json.load(open('ml/results/metrics.json'))
          mape = m['test_mape']
          print(f'MAPE={mape:.4f}  MAE={m[\"test_mae\"]:,.0f} VND')
          if mape > 0.15:
              print('FAIL: MAPE exceeds 15% threshold')
              sys.exit(1)
          print('PASS')
          "
      - uses: actions/github-script@v7
        if: github.event_name == 'pull_request'
        with:
          script: |
            const m = require('./ml/results/metrics.json')
            const body = [
              '### 📊 ML Eval Results',
              `- MAPE: ${(m.test_mape * 100).toFixed(2)}%`,
              `- MAE: ${m.test_mae.toLocaleString('vi-VN')} VND`,
              `- R²: ${m.r2.toFixed(3)}`
            ].join('\n')
            github.rest.issues.createComment({
              issue_number: context.issue.number, body
            })

  build-and-push:
    runs-on: ubuntu-latest
    needs: [test-unit, test-integration, dbt-test]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          context: api/
          push: true
          tags: ghcr.io/${{ github.repository }}/api:${{ github.sha }},ghcr.io/${{ github.repository }}/api:latest
```

---

## 16. Infrastructure

### 16.1 Docker Compose

```yaml
# docker-compose.yml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: jobradarvn
      POSTGRES_USER: jobradarvn
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes: [pgdata:/var/lib/postgresql/data]
    ports: ["5432:5432"]
    healthcheck:
      test: [CMD, pg_isready, -U, jobradarvn]
      interval: 10s

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  api:
    build: ./api
    ports: ["8000:8000"]
    env_file: .env
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }

  worker-nlp:
    build: .
    command: celery -A workers.celery_app worker -Q nlp,scraping --concurrency=4
    env_file: .env
    depends_on: [db, redis]

  worker-alerts:
    build: .
    command: celery -A workers.celery_app worker -Q alerts --concurrency=2
    env_file: .env
    depends_on: [db, redis]

  beat:
    build: .
    command: celery -A workers.celery_app beat --loglevel=info
    env_file: .env
    depends_on: [redis]

  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    command: mlflow server --host 0.0.0.0 --backend-store-uri sqlite:///mlruns/mlflow.db
    volumes: [mlruns:/mlruns]
    ports: ["5000:5000"]

  prometheus:
    image: prom/prometheus:latest
    volumes: ["./infra/prometheus:/etc/prometheus"]
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana:latest
    ports: ["3001:3000"]
    environment: { GF_SECURITY_ADMIN_PASSWORD: admin }
    volumes: [grafana_data:/var/lib/grafana, "./infra/grafana:/etc/grafana/provisioning"]

  web:
    build: ./web
    ports: ["3000:3000"]
    environment: { NEXT_PUBLIC_API_URL: http://api:8000 }

volumes: [pgdata, mlruns, grafana_data]
```

### 16.2 Cost Estimate

| Tier | Stack | Cost/month | Notes |
|------|-------|-----------|-------|
| **Local Dev** | Docker Compose | $0 | Full stack on laptop |
| **Staging** | Railway Hobby | ~$5 | API + Worker only |
| **Prod (Small)** | Railway Pro + Railway PG | ~$25-40 | Up to 10k users, 100k jobs |
| **Prod (Scale)** | Hetzner CX33 | Verify current regional price | Self-hosted, ~1M jobs |
| **Prod (HA)** | 2× Hetzner CX33 + Cloudflare | Verify current regional price | High availability |

### 16.3 `.env.example`

```bash
# Database
DATABASE_URL=postgresql+asyncpg://jobradarvn:changeme@localhost:5432/jobradarvn
DB_PASSWORD=changeme

# Redis
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET_KEY=change_to_random_32_char_string_minimum
ADMIN_API_KEY=change_to_random_admin_key

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_EXPERIMENT_NAME=jobradarvn-salary

# External APIs
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=

# Notifications
TELEGRAM_BOT_TOKEN=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=

# App
APP_ENV=development
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
MAX_JOBS_PER_PAGE=50
```

---

## 17. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|-----------|
| 1 | ITViec/Shopee blocks scraper | High | High | Conservative rate limiting; fallback: partner API, manual data entry |
| 2 | Salary data sparse (many jobs don't disclose salary) | High | Medium | Use disclosed data + confidence flag; supplement with community salary survey |
| 3 | Vietnamese NLP accuracy low on tech jargon | Medium | Medium | `underthesea` + domain-specific rules; manual sample review; F1 monitoring |
| 4 | `all-MiniLM` semantic quality for VN job text | Medium | Medium | A/B test vs keyword TF-IDF matching; use hybrid scoring |
| 5 | Cold start: < 5 jobs per role → no salary band | High | Medium | Show "not enough data" gracefully; aggregate at category level |
| 6 | pgvector HNSW slow at > 500k vectors | Low | Medium | Pre-filter by date/location before vector search; partition embeddings |
| 7 | CV PII leak | Low | High | RLS policy, no analytics inclusion, deletable; pgcrypto AES-256 at rest |
| 8 | Model drift: salary distribution shifts | Medium | Medium | Weekly retraining; MAPE gauge in Grafana; alert at MAPE > 20% |

---

## 18. MVP Definition

### MVP Scope (Phase 0-2, Tuần 0-5)

**In Scope:**
- [x] ITViec scraper (1 platform, public listings only)
- [x] PostgreSQL schema + pgvector extension
- [x] Basic NLP: skill extraction + title normalization
- [x] dbt: staging + intermediate models (ITViec only)
- [x] `mart_salary_bands` + `mart_skill_demand` materialized
- [x] FastAPI: `/api/jobs`, `/api/salary/bands`, `/api/analytics/skills/demand`
- [x] Salary bands: rule-based (from mart) — NO ML predictor yet
- [x] Next.js: job search page + salary calculator (rule-based)
- [x] Docker Compose: db + redis + api + worker + beat

**Out of Scope for MVP:**
- ❌ TopCV / VietnamWorks / LinkedIn
- ❌ XGBoost ML salary predictor (Phase 3)
- ❌ pgvector matching (Phase 3)
- ❌ User accounts + JWT (Phase 3)
- ❌ Job alerts (Phase 3)
- ❌ Grafana monitoring (Phase 5)

### Definition of Done — MVP

MVP is **done** when ALL of the following pass:
1. ✅ ≥ 500 real IT jobs from ITViec indexed in DB
2. ✅ Salary bands visible for ≥ 10 normalized roles
3. ✅ `/api/jobs` returns results in < 500ms (p95)
4. ✅ Frontend loads in < 3s on localhost
5. ✅ `dbt test` passes 100%
6. ✅ Unit test coverage ≥ 60%
7. ✅ `docker compose up` starts all services without error

---

## 19. Roadmap

### Phase 0 — Validate (3 ngày)
- [x] Test ITViec scraping: 20 pages manually, confirm parseable
- [x] Benchmark the selected extractor on 50 job descriptions (target F1 > 0.80)
- [x] Confirm pgvector HNSW available on target PostgreSQL
- [x] Time `all-MiniLM-L6-v2` inference on CPU (target < 100ms/doc)
- [x] Decision: proceed or adjust stack

### Phase 1 — Foundation (Tuần 1-2)
- [x] Repo setup: pyproject.toml, ruff, mypy, pre-commit
- [x] Docker Compose: db, redis, api, worker, beat
- [x] PostgreSQL schema + alembic migrations
- [x] ITViec scraper (list + detail pages)
- [x] Pydantic validation for raw jobs
- [x] Celery + Redis: basic task flow
- [x] FastAPI skeleton: `/health`, `/health/ready`

### Phase 2 — NLP & Data Engineering (Tuần 3-5)
- [x] Salary parser (all VN formats)
- [x] Skill extractor (versioned 3,336-entry taxonomy)
- [x] Title normalizer (30+ patterns)
- [x] dbt: staging models (ITViec)
- [x] dbt: intermediate (unified jobs, salary normalized)
- [x] dbt: marts (salary_bands, skill_demand)
- [x] dbt tests (freshness + constraints)
- [x] Prefect: daily ingestion flow
- [x] **MVP COMPLETE** ← checkpoint here

### Phase 3 — ML Pipeline (Tuần 6-8)
- [x] Feature engineering: encode level, location, skills
- [x] XGBoost × 3 (mean + Q25 + Q75): train + MLflow log
- [x] ML evaluation CI gate (MAPE < 15%; current clean-room result 11.66%)
- [x] pgvector: embed all jobs with all-MiniLM-L6-v2
- [x] Job matching API: `/api/profile/matching-jobs`
- [x] Skill gap analyzer

### Phase 4 — Multi-source + Full Application (Tuần 9-11)
- [x] VietnamWorks scraper (first-party search pagination, 425 current jobs verified)
- [x] TopCV scraper (broad IT route: 465 jobs, zero final errors; challenge path fails closed)
- [x] User auth (JWT + httpOnly cookie)
- [x] Job alerts (Celery Beat + Telegram Bot)
- [x] CV upload + text extraction + embedding
- [x] Next.js: complete all pages

### Phase 5 — Production (Tuần 12-14)
- [x] Prometheus + Grafana dashboards (5 dashboards)
- [x] Alert rules: ScraperSilent, ModelDrift, QueueBacklog
- [x] Full GitHub Actions CI/CD (immutable images, gated deploy, smoke and rollback)
- [x] Rate limiting: auth-aware (anon vs authenticated)
- [x] Load test with k6 (target: 100 RPS, p95 < 500ms)
- [x] Full documentation (README + API docs + data dictionary)
- [ ] Deploy: apply validated Terraform and release Docker Compose on Hetzner CX33

---

*Version 1.6 - ML PUBLICATION READY | 2026-07-19 | Acceptance evidence in `docs/completion_audit.md`*
