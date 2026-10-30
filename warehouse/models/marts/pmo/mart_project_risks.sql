-- Risk findings per in-flight project, evaluated on the as-of date. Same rules as the
-- PMO platform's risk page:
--   delivery   milestone overdue (high if > overdue_high_days); folded into closure once past end
--   schedule   share of time used minus share of milestones delivered >= gap thresholds
--   closure    planned end date passed (high)
--   deadline   planned end within deadline_warning_days with deliverables open (mid)
--   resource   owner has left (high), no executors (mid)
--   extension  extended extensions_mid / extensions_high times or more
--   silence    no update for silence_low_days / silence_mid_days
--   reported   the latest update (within silence_low_days) reads red or blocked, judged from the
--              text by the stage 5 extractor; only present once an extraction has run
-- Strategic projects are raised one level. Paused projects are not scored.
with as_of as (
    select as_of_date from {{ ref('int_as_of_date') }}
),

projects as (
    select p.*, f.milestones_planned, f.milestones_accepted, f.days_since_update
    from {{ ref('dim_project') }} as p
    join {{ ref('fct_projects') }} as f using (project_id)
    where p.status in ('not_started', 'active', 'to_report')
),

overdue as (
    select project_id, count(*) as overdue_count, max(days_overdue) as max_days_overdue
    from {{ ref('fct_milestones') }}
    where is_overdue
    group by project_id
),

reported as (
    select project_id, extracted_rag, extracted_blocked, extractor, posted_at
    from {{ ref('fct_status_update_signals') }}
    where is_latest_for_project
),

open_deliverables as (
    select project_id, count(*) as open_count
    from {{ ref('fct_milestones') }}
    where milestone_status in ('open', 'returned', 'submitted')
    group by project_id
),

base as (
    select
        p.*,
        a.as_of_date,
        p.status in ('active', 'to_report') as is_running,
        case when p.status = 'active' and p.planned_end < a.as_of_date then a.as_of_date - p.planned_end else 0 end as days_past_end,
        coalesce(o.overdue_count, 0) as overdue_count,
        o.max_days_overdue,
        coalesce(d.open_count, 0) as open_count,
        case
            when p.start_date is not null and p.planned_end > p.start_date
            then round(100 * least(1, greatest(0, (a.as_of_date - p.start_date) / (p.planned_end - p.start_date)::double)))
        end as pct_time_used,
        round(100 * p.milestones_accepted / nullif(p.milestones_planned, 0)) as pct_delivered,
        rp.extracted_rag,
        rp.extracted_blocked,
        rp.extractor as signal_extractor,
        a.as_of_date - rp.posted_at::date as days_since_signal
    from projects as p
    cross join as_of as a
    left join reported as rp using (project_id)
    left join overdue as o using (project_id)
    left join open_deliverables as d using (project_id)
),

findings as (
    select project_id, 'delivery' as category,
        case when max_days_overdue > {{ var('overdue_high_days') }} then 'high' else 'mid' end as base_level,
        overdue_count || ' milestone(s) overdue, up to ' || max_days_overdue || ' days' as finding
    from base where is_running and overdue_count > 0 and days_past_end = 0

    union all
    select project_id, 'schedule',
        case when pct_time_used - pct_delivered >= {{ var('schedule_gap_high_pct') }} then 'high' else 'mid' end,
        pct_time_used || '% of time used, ' || pct_delivered || '% delivered'
    from base
    where is_running and milestones_planned > 1 and pct_time_used - pct_delivered >= {{ var('schedule_gap_mid_pct') }}

    union all
    select project_id, 'closure', 'high', days_past_end || ' days past planned end'
    from base where days_past_end > 0

    union all
    select project_id, 'deadline', 'mid', (planned_end - as_of_date) || ' days to planned end, ' || open_count || ' deliverable(s) open'
    from base
    where status = 'active' and planned_end - as_of_date between 0 and {{ var('deadline_warning_days') }} and open_count > 0

    union all
    select project_id, 'resource', 'high', 'owner has left the company'
    from base where owner_has_left

    union all
    select project_id, 'resource', 'mid', 'no executor assigned'
    from base where status = 'active' and executor_count = 0

    union all
    select project_id, 'extension',
        case when extension_count >= {{ var('extensions_high') }} then 'high' else 'mid' end,
        'extended ' || extension_count || ' times'
    from base where extension_count >= {{ var('extensions_mid') }}

    union all
    select project_id, 'reported', 'high',
        'latest update reads ' || case when extracted_blocked then 'blocked' else 'red' end || ' (' || signal_extractor || ')'
    from base
    where is_running and (extracted_rag = 'red' or extracted_blocked) and days_since_signal <= {{ var('silence_low_days') }}

    union all
    select project_id, 'silence',
        case when days_since_update > {{ var('silence_mid_days') }} then 'mid' else 'low' end,
        coalesce('no update for ' || days_since_update || ' days', 'no update yet')
    from base
    where status = 'active' and (days_since_update is null or days_since_update > {{ var('silence_low_days') }})
),

leveled as (
    select
        f.*,
        case
            when b.is_strategic and f.base_level = 'mid' then 'high'
            when b.is_strategic and f.base_level = 'low' then 'mid'
            else f.base_level
        end as risk_level,
        b.project_code, b.team_code, b.office, b.status, b.is_strategic, b.owner_name, b.as_of_date
    from findings as f
    join base as b using (project_id)
)

select
    project_id || '-' || category || '-' || row_number() over (partition by project_id, category order by finding) as finding_key,
    project_id,
    project_code,
    team_code,
    office,
    status,
    is_strategic,
    owner_name,
    category,
    risk_level,
    finding,
    -- each project is labelled with one main risk: the most severe, then by this category order
    row_number() over (
        partition by project_id
        order by case risk_level when 'high' then 0 when 'mid' then 1 else 2 end,
            list_position(['resource', 'closure', 'delivery', 'reported', 'schedule', 'deadline', 'extension', 'silence'], category)
    ) = 1 as is_main_risk,
    as_of_date
from leveled
