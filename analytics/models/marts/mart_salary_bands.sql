{{ config(post_hook='analyze {{ this }}') }}

select
    title_normalized,
    job_level,
    location,
    count(*) as n_jobs,
    percentile_cont(0.25) within group (order by salary_midpoint_vnd) as p25,
    percentile_cont(0.50) within group (order by salary_midpoint_vnd) as median,
    percentile_cont(0.75) within group (order by salary_midpoint_vnd) as p75,
    avg(salary_midpoint_vnd) as mean,
    array_agg(distinct source order by source) as sources,
    min(source_snapshot_date) as period_start,
    max(source_snapshot_date) as period_end,
    current_timestamp as updated_at
from {{ ref('int_salary_normalized') }}
where salary_disclosed
  and salary_midpoint_vnd between 1000000 and 200000000
group by title_normalized, job_level, location
having count(*) >= 3
