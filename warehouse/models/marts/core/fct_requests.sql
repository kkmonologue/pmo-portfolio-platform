-- One row per request version, with PMO decision time.
select
    r.request_id,
    r.request_kind,
    r.project_id,
    r.project_code,
    t.team_code,
    t.office,
    r.change_types,
    r.is_extension,
    r.is_owner_change,
    r.is_executor_change,
    r.requested_title,
    r.requested_strategic_level,
    r.requested_new_end,
    r.request_version,
    r.request_status,
    r.submitted_by_id,
    r.submitted_at,
    r.decided_by_id,
    r.decided_at,
    round(r.decision_days, 2) as decision_days,
    r.is_open,
    r.decision_comment
from {{ ref('int_request_cycle_times') }} as r
join {{ ref('stg_app__teams') }} as t using (team_id)
