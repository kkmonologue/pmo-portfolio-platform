select
    vote_id,
    review_id,
    person_id,
    vote,
    comment,
    voted_at,
    updated_at
from {{ source('app', 'board_votes') }}
