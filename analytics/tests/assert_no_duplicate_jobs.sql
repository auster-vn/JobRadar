select platform, platform_job_id, count(*)
from {{ ref('int_unified_jobs') }}
group by platform, platform_job_id
having count(*) > 1
