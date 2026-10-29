-- One row per milestone of a live project, with lateness and the evidence workflow.
with as_of as (select as_of_date from {{ ref('int_as_of_date') }})

select
    m.milestone_id,
    m.project_id,
    p.project_code,
    p.team_code,
    m.milestone_seq,
    m.milestone_name,
    m.milestone_seq = max(m.milestone_seq) over (partition by m.project_id) as is_final_milestone,
    m.evidence_forms,
    m.milestone_status,
    m.original_due_date,
    m.due_date,
    m.days_moved,
    m.accepted_on,
    m.accepted_on - m.original_due_date as days_late_vs_original,
    m.accepted_on <= m.original_due_date as delivered_on_time,
    m.milestone_status in ('open', 'returned') and m.due_date < a.as_of_date and p.status in ('active', 'to_report') as is_overdue,
    case when m.milestone_status in ('open', 'returned') and m.due_date < a.as_of_date then a.as_of_date - m.due_date end as days_overdue,
    e.submissions,
    e.times_returned,
    e.first_submitted_at,
    e.avg_review_days
from {{ ref('stg_app__milestones') }} as m
join {{ ref('dim_project') }} as p using (project_id)
left join {{ ref('int_milestone_evidence') }} as e using (milestone_id)
cross join as_of as a
