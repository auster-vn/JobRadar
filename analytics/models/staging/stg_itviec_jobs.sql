with source as (
    select * from {{ source('application', 'jobs') }}
    where platform = 'itviec'
)

select
    id as job_id,
    company_id,
    platform,
    platform_job_id,
    source_url,
    trim(title) as title,
    title_normalized,
    job_level,
    job_type,
    location,
    salary_min,
    salary_max,
    salary_negotiable,
    salary_currency,
    description_cleaned,
    skills_required,
    skills_nice_to_have,
    experience_years_min,
    experience_years_max,
    posted_at,
    expires_at,
    is_active,
    created_at,
    updated_at
from source
