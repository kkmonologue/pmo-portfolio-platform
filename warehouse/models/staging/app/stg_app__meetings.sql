select
    meeting_id,
    meeting_date,
    track as meeting_track,
    updated_at
from {{ source('app', 'meetings') }}
