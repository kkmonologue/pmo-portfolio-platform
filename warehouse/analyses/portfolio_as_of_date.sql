-- Point-in-time view of the portfolio using the SCD2 history: how many projects were in
-- each status on a given day, and who owned them. Change the date and run:
--   uv run dbt compile --project-dir warehouse --profiles-dir warehouse --select portfolio_as_of_date
-- then paste the compiled SQL (warehouse/target/compiled/...) into DuckDB.
{% set as_of = '2025-12-31' %}

select
    h.status,
    count(*) as projects,
    count(*) filter (where o.is_departed and o.departed_on <= date '{{ as_of }}') as owned_by_people_who_had_left
from {{ ref('dim_project_history') }} as h
left join {{ ref('dim_person') }} as o on h.owner_id = o.person_id
where h.valid_from <= timestamp '{{ as_of }} 23:59:59'
  and (h.valid_to > timestamp '{{ as_of }} 23:59:59' or h.valid_to is null)
group by h.status
order by projects desc
