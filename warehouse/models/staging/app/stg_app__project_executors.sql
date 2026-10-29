select
    executor_id,
    project_id,
    person_id,
    executor_name,
    person_id is null as is_external,
    removed as is_removed,
    created_at as added_at,
    updated_at
from {{ source('app', 'project_executors') }}
