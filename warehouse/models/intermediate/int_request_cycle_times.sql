-- Request versions with PMO cycle time. A returned request comes back as a new version.
select
    r.*,
    date_diff('hour', r.submitted_at, r.decided_at) / 24.0 as decision_days,
    r.request_status = 'pending' as is_open,
    p.project_code
from {{ ref('stg_app__requests') }} as r
left join {{ ref('stg_app__projects') }} as p using (project_id)
