select
    companies.id as company_id,
    companies.name as company_name,
    date_trunc('month', jobs.posted_at) as month,
    count(*) as jobs_posted,
    count(*) filter (where jobs.salary_min is not null or jobs.salary_max is not null)
        as jobs_with_salary
from {{ ref('int_unified_jobs') }} as jobs
inner join {{ source('application', 'companies') }} as companies
    on companies.id = jobs.company_id
where jobs.posted_at >= current_timestamp - interval '12 months'
group by companies.id, companies.name, date_trunc('month', jobs.posted_at)
