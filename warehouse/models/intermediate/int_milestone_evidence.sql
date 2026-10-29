-- Evidence workflow per milestone: how often it was submitted and returned, and timing.
with subs as (
    select
        milestone_id,
        count(*) as submissions,
        count(*) filter (where review_status = 'returned') as times_returned,
        min(submitted_at) as first_submitted_at,
        max(reviewed_at) filter (where review_status = 'accepted') as accepted_at,
        avg(date_diff('hour', submitted_at, reviewed_at)) filter (where reviewed_at is not null) / 24.0 as avg_review_days
    from {{ ref('stg_app__milestone_submissions') }}
    group by milestone_id
)

select
    m.milestone_id,
    m.project_id,
    coalesce(s.submissions, 0) as submissions,
    coalesce(s.times_returned, 0) as times_returned,
    s.first_submitted_at,
    s.accepted_at,
    s.avg_review_days
from {{ ref('stg_app__milestones') }} as m
left join subs as s using (milestone_id)
