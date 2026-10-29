-- One row per period a project spent in a status, rebuilt from the event log.
with changes as (
    select
        project_id,
        event_at as valid_from,
        new_value as status,
        event_id
    from {{ ref('stg_app__project_events') }}
    where event_type in ('created', 'status')
)

select
    project_id,
    status,
    valid_from,
    lead(valid_from) over (partition by project_id order by valid_from, event_id) as valid_to,
    row_number() over (partition by project_id order by valid_from, event_id) as status_seq,
    lead(valid_from) over (partition by project_id order by valid_from, event_id) is null as is_current
from changes
