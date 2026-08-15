select
    record_id,
    source,
    is_live,
    source_snapshot_date,
    title_normalized,
    job_level,
    location,
    experience_years,
    skills,
    salary_min as salary_min_vnd,
    salary_max as salary_max_vnd,
    case
        when salary_min is not null and salary_max is not null
            then (salary_min + salary_max) / 2
        else coalesce(salary_min, salary_max)
    end as salary_midpoint_vnd,
    salary_min is not null or salary_max is not null as salary_disclosed
from {{ source('application', 'salary_market_data') }}
where (is_live and source_snapshot_date >= current_date - interval '6 months')
   or (not is_live and source_snapshot_date >= current_date - interval '24 months')
