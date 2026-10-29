-- One row per bi-weekly update: which meeting it was for and whether it arrived in time.
select
    u.update_id,
    u.project_id,
    p.project_code,
    p.team_code,
    p.office,
    u.author_id,
    u.author_id = p.owner_id as written_by_owner,
    u.meeting_id,
    m.meeting_date,
    m.meeting_track,
    u.posted_at,
    m.meeting_date - u.posted_at::date as days_before_meeting,
    u.posted_at::date < m.meeting_date as posted_before_meeting,
    u.body,
    u.body_chars
from {{ ref('stg_app__status_updates') }} as u
join {{ ref('dim_project') }} as p using (project_id)
left join {{ ref('stg_app__meetings') }} as m using (meeting_id)
