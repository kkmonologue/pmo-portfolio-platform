select
    event_id,
    project_id,
    event_at,
    actor_id,
    event_type,
    old_value,
    new_value,
    note,
    updated_at
from {{ source('app', 'project_events') }}
