-- SCD type 2: one row per version of a project. A new version starts whenever the
-- status, the owner or the planned end date changes. Rebuilt from the event log, so it
-- also covers history that happened before the warehouse existed.
with events as (
    select * from {{ ref('stg_app__project_events') }}
),

end_changes as (
    select project_id, event_at, event_id, cast(new_value as date) as planned_end
    from events
    where event_type = 'end_date'
),

projects as (
    select
        p.project_id,
        p.original_end,
        -- projects approved before they were planned had no end date until the plan event
        exists (select 1 from events as e where e.project_id = p.project_id and e.event_type = 'end_date' and e.old_value is null) as planned_later
    from {{ ref('stg_app__projects') }} as p
    where not p.is_deleted
),

change_points as (
    select project_id, valid_from as changed_at from {{ ref('int_project_status_history') }}
    union
    select project_id, valid_from from {{ ref('int_project_owner_history') }}
    union
    select project_id, event_at from end_changes
),

versions as (
    select
        c.project_id,
        c.changed_at as valid_from,
        lead(c.changed_at) over (partition by c.project_id order by c.changed_at) as valid_to,
        s.status,
        o.owner_id,
        coalesce(e.planned_end, case when p.planned_later then null else p.original_end end) as planned_end
    from change_points as c
    join projects as p using (project_id)
    asof left join {{ ref('int_project_status_history') }} as s
        on c.project_id = s.project_id and c.changed_at >= s.valid_from
    asof left join {{ ref('int_project_owner_history') }} as o
        on c.project_id = o.project_id and c.changed_at >= o.valid_from
    asof left join end_changes as e
        on c.project_id = e.project_id and c.changed_at >= e.event_at
)

select
    project_id || '-' || row_number() over (partition by project_id order by valid_from) as project_version_key,
    project_id,
    row_number() over (partition by project_id order by valid_from) as version_no,
    valid_from,
    valid_to,
    valid_to is null as is_current,
    status,
    owner_id,
    planned_end
from versions
