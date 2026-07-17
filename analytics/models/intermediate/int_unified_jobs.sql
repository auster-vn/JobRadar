{{ config(materialized='incremental', unique_key='job_id') }}

with unified as (
    select * from {{ ref('stg_itviec_jobs') }}
    union all
    select * from {{ ref('stg_topcv_jobs') }}
    union all
    select * from {{ ref('stg_vietnamworks_jobs') }}
)

select * from unified

{% if is_incremental() %}
where updated_at >= (
    select coalesce(max(updated_at) - interval '3 days', '1970-01-01') from {{ this }}
)
{% endif %}
