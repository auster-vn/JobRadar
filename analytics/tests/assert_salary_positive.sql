select *
from {{ ref('int_salary_normalized') }}
where salary_midpoint_vnd <= 0
