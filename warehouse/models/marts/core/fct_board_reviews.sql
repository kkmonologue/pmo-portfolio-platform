-- One row per board voting round on a strategic project request.
with votes as (
    select
        review_id,
        count(*) as votes_cast,
        count(*) filter (where vote = 'yes') as votes_yes,
        count(*) filter (where vote = 'no') as votes_no,
        max(voted_at) as last_vote_at
    from {{ ref('stg_app__board_votes') }}
    group by review_id
)

select
    b.review_id,
    b.request_id,
    r.requested_title,
    t.team_code,
    b.strategic_level,
    b.review_round,
    b.review_status,
    b.sent_at,
    b.closed_at,
    round(date_diff('hour', b.sent_at, b.closed_at) / 24.0, 1) as days_to_outcome,
    coalesce(v.votes_cast, 0) as votes_cast,
    coalesce(v.votes_yes, 0) as votes_yes,
    coalesce(v.votes_no, 0) as votes_no
from {{ ref('stg_app__board_reviews') }} as b
join {{ ref('stg_app__requests') }} as r using (request_id)
join {{ ref('stg_app__teams') }} as t on r.team_id = t.team_id
left join votes as v using (review_id)
