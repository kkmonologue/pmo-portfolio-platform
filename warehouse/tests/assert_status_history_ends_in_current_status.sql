-- The rebuilt status history must end in each project's current status.
select h.project_id, h.status as history_status, p.status as current_status
from {{ ref('int_project_status_history') }} as h
join {{ ref('stg_app__projects') }} as p using (project_id)
where h.is_current and h.status <> p.status
