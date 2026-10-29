select
    request_id,
    kind as request_kind,
    project_id,
    team_id,
    change_types,
    coalesce(change_types like '%end%', false) as is_extension,
    coalesce(change_types like '%owner%', false) as is_owner_change,
    coalesce(change_types like '%exec%', false) as is_executor_change,
    -- what was asked for, unpacked from the JSON payload
    json_extract_string(payload, '$.title') as requested_title,
    json_extract_string(payload, '$.level') as requested_strategic_level,
    try_cast(json_extract_string(payload, '$.new_end') as date) as requested_new_end,
    try_cast(json_extract_string(payload, '$.new_owner_id') as integer) as requested_owner_id,
    reason,
    submitted_by as submitted_by_id,
    submitted_at,
    version as request_version,
    status as request_status,
    decided_by as decided_by_id,
    decided_at,
    decision_comment,
    updated_at
from {{ source('app', 'requests') }}
