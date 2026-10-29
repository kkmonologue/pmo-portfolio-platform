-- One row per team: what is running, how healthy it is and how well it reports.
with p as (
    select * from {{ ref('fct_projects') }}
),

risks as (
    select team_code, count(distinct project_id) filter (where risk_level = 'high' and is_main_risk) as high_risk_projects
    from {{ ref('mart_project_risks') }}
    group by team_code
),

as_of as (select as_of_date from {{ ref('int_as_of_date') }})

select
    t.team_code,
    t.team_name,
    t.office,
    t.region,
    count(p.project_id) filter (where p.outcome = 'in_flight') as projects_in_flight,
    count(p.project_id) filter (where p.status = 'active') as projects_active,
    count(p.project_id) filter (where p.status = 'on_hold') as projects_on_hold,
    count(p.project_id) filter (where p.status = 'to_report') as projects_awaiting_close,
    count(p.project_id) filter (where p.status = 'closed' and p.actual_end >= a.as_of_date - 90) as closed_last_90_days,
    count(p.project_id) filter (where p.status = 'canceled' and p.actual_end >= a.as_of_date - 90) as canceled_last_90_days,
    coalesce(max(r.high_risk_projects), 0) as high_risk_projects,
    coalesce(sum(p.milestones_overdue), 0) as milestones_overdue,
    round(avg(p.extension_count) filter (where p.outcome <> 'in_flight'), 2) as avg_extensions_finished,
    round(avg(case when p.days_since_update <= 30 then 1.0 else 0.0 end) filter (where p.status = 'active'), 3) as share_active_updated_30d
from {{ ref('dim_team') }} as t
cross join as_of as a
left join p on p.team_code = t.team_code
left join risks as r on r.team_code = t.team_code
where t.office <> 'pmo'
group by all
