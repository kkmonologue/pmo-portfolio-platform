-- One row per live project with delivery, change and reporting figures.
with ms as (
    select
        project_id,
        count(*) filter (where milestone_status <> 'dropped') as milestones_planned,
        count(*) filter (where milestone_status = 'accepted') as milestones_accepted,
        count(*) filter (where is_overdue) as milestones_overdue,
        sum(times_returned) as evidence_returns
    from {{ ref('fct_milestones') }}
    group by project_id
),

upd as (
    select project_id, count(*) as status_updates, max(posted_at) as last_update_at
    from {{ ref('stg_app__status_updates') }}
    group by project_id
),

req as (
    select
        project_id,
        count(*) filter (where request_kind = 'change') as change_requests,
        count(*) filter (where request_kind = 'change' and request_status = 'approved') as changes_approved,
        count(*) filter (where request_kind = 'close') as close_requests,
        count(*) filter (where request_status = 'returned') as requests_returned
    from {{ ref('stg_app__requests') }}
    where project_id is not null
    group by project_id
),

as_of as (
    select as_of_date from {{ ref('int_as_of_date') }}
)

select
    p.project_id,
    p.project_code,
    p.team_code,
    p.office,
    p.region,
    p.status,
    case when p.status in ('closed', 'canceled') then p.status else 'in_flight' end as outcome,
    p.is_strategic,
    p.strategic_level,
    p.owner_id,
    p.start_date,
    p.original_end,
    p.planned_end,
    p.actual_end,
    p.original_end - p.start_date as planned_duration_days,
    coalesce(p.actual_end, a.as_of_date) - p.start_date as elapsed_days,
    p.extension_count,
    p.extension_count > 0 as was_extended,
    p.days_extended,
    coalesce(ms.milestones_planned, 0) as milestones_planned,
    coalesce(ms.milestones_accepted, 0) as milestones_accepted,
    coalesce(ms.milestones_overdue, 0) as milestones_overdue,
    round(coalesce(ms.milestones_accepted, 0) / nullif(ms.milestones_planned, 0), 3) as delivery_ratio,
    coalesce(ms.evidence_returns, 0) as evidence_returns,
    coalesce(u.status_updates, 0) as status_updates,
    u.last_update_at,
    a.as_of_date - u.last_update_at::date as days_since_update,
    coalesce(r.change_requests, 0) as change_requests,
    coalesce(r.changes_approved, 0) as changes_approved,
    coalesce(r.close_requests, 0) as close_requests,
    coalesce(r.requests_returned, 0) as requests_returned
from {{ ref('dim_project') }} as p
cross join as_of as a
left join ms using (project_id)
left join upd as u using (project_id)
left join req as r using (project_id)
