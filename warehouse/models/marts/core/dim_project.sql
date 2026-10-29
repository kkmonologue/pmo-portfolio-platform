-- Current attributes of every live (not soft-deleted) project.
with executors as (
    select
        project_id,
        count(*) filter (where not is_removed) as executor_count,
        count(*) filter (where not is_removed and is_external) as external_executor_count
    from {{ ref('stg_app__project_executors') }}
    group by project_id
)

select
    p.project_id,
    p.project_code,
    p.legacy_code,
    p.project_title,
    p.scope,
    p.section,
    t.team_code,
    t.team_name,
    t.office,
    t.region,
    p.status,
    p.strategic_level,
    p.is_strategic,
    p.owner_id,
    o.display_name as owner_name,
    p.owner_name_typed,
    coalesce(o.is_departed, false) as owner_has_left,
    coalesce(e.executor_count, 0) as executor_count,
    coalesce(e.external_executor_count, 0) as external_executor_count,
    p.start_date,
    p.original_end,
    p.planned_end,
    p.actual_end,
    p.extension_count,
    p.days_extended,
    p.created_at
from {{ ref('stg_app__projects') }} as p
join {{ ref('stg_app__teams') }} as t using (team_id)
left join {{ ref('stg_app__people') }} as o on p.owner_id = o.person_id
left join executors as e using (project_id)
where not p.is_deleted
