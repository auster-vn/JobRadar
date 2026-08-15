with monthly as (
    select
        skill,
        date_trunc('month', posted_at) as month,
        count(*) as job_count
    from {{ ref('int_job_skills') }}
    where is_active and posted_at >= current_timestamp - interval '12 months'
    group by skill, date_trunc('month', posted_at)
), with_trend as (
    select
        *,
        sum(job_count) over (partition by skill) as total_12m,
        lag(job_count) over (partition by skill order by month) as previous_count
    from monthly
)

select
    skill,
    month,
    job_count,
    total_12m,
    dense_rank() over (order by total_12m desc) as demand_rank,
    round((job_count - previous_count)::numeric / nullif(previous_count, 0) * 100, 2)
        as mom_growth_pct
from with_trend
where total_12m >= 3
