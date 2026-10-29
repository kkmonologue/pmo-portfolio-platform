select
    follow_up_id,
    code as follow_up_code,
    team_id,
    follow_up_type,
    title as follow_up_title,
    owner_id,
    source_project_id,
    converted_project_id,
    status as follow_up_status,
    created_at::date as opened_on,
    closed_on,
    updated_at
from {{ source('app', 'follow_ups') }}
