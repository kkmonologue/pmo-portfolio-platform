select
    review_id,
    request_id,
    level as strategic_level,
    round as review_round,
    sent_at,
    status as review_status,
    closed_at,
    updated_at
from {{ source('app', 'board_reviews') }}
