-- One row per period a person owned a project. The owner before the first hand-over is
-- the old_value of the first owner event; projects that never changed owner have one period.
with projects as (
    select project_id, owner_id, created_at from {{ ref('stg_app__projects') }}
),

handovers as (
    select
        project_id,
        event_at,
        event_id,
        cast(old_value as integer) as old_owner_id,
        cast(new_value as integer) as new_owner_id
    from {{ ref('stg_app__project_events') }}
    where event_type = 'owner'
),

first_owner as (
    select
        p.project_id,
        coalesce(
            (select h.old_owner_id from handovers as h where h.project_id = p.project_id order by h.event_at, h.event_id limit 1),
            p.owner_id
        ) as owner_id,
        p.created_at as valid_from,
        0 as event_id
    from projects as p
),

periods as (
    select project_id, owner_id, valid_from, event_id from first_owner
    union all
    select project_id, new_owner_id, event_at, event_id from handovers
)

select
    project_id,
    owner_id,
    valid_from,
    lead(valid_from) over (partition by project_id order by valid_from, event_id) as valid_to,
    lead(valid_from) over (partition by project_id order by valid_from, event_id) is null as is_current
from periods
