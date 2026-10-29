-- The current SCD2 version must carry the project's current status, owner and planned end.
select h.project_id
from {{ ref('dim_project_history') }} as h
join {{ ref('dim_project') }} as p using (project_id)
where h.is_current
  and (h.status <> p.status or h.owner_id <> p.owner_id or h.planned_end is distinct from p.planned_end)
