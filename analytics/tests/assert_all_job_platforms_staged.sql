with source_platforms as (
    select distinct platform
    from {{ source('application', 'jobs') }}
), staged_platforms as (
    select distinct platform
    from {{ ref('int_unified_jobs') }}
)

select source_platforms.platform
from source_platforms
left join staged_platforms using (platform)
where staged_platforms.platform is null
