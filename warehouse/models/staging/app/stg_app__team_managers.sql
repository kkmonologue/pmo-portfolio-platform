select
    team_manager_id,
    team_id,
    person_id,
    section,
    valid_from,
    valid_to,
    valid_to is null as is_current,
    updated_at
from {{ source('app', 'team_managers') }}
