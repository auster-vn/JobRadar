select
    job_id,
    unnest(skills_required) as skill,
    posted_at,
    is_active
from {{ ref('int_unified_jobs') }}
