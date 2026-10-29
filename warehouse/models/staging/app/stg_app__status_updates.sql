select
    update_id,
    project_id,
    meeting_id,
    author_id,
    posted_at,
    body,
    length(body) as body_chars,
    updated_at
from {{ source('app', 'status_updates') }}
