select
    team_id,
    code as team_code,
    name_en as team_name,
    team_group,
    case team_group when 'R' then 'front' when 'C' then 'middle' else 'pmo' end as office,
    region,
    meeting_track,
    created_at,
    updated_at
from {{ source('app', 'teams') }}
