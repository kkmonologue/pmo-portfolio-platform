-- Latest legacy tracker snapshot reconciled against the system. One row per project the
-- tracker should list (in flight, or finished within 120 days) and per tracker row that
-- does not match any project.
--   ok                  listed, status compatible, same planned end
--   status_mismatch     tracker status cannot stand for the system status (often stale)
--   end_date_mismatch   status fine, planned end differs
--   missing_in_tracker  the system has it, the sheet does not
--   not_in_system       the sheet lists a reference the system does not know
with latest as (
    select max(snapshot_week) as snapshot_week, max(snapshot_date) as snapshot_date
    from {{ ref('stg_tracker__rows') }}
),

rows as (
    select r.*
    from {{ ref('int_tracker_rows_matched') }} as r
    join latest using (snapshot_week)
),

expected as (
    select p.project_id, p.project_code, p.team_code, p.status, p.planned_end, p.extension_count
    from {{ ref('dim_project') }} as p
    cross join latest as l
    where p.created_at::date <= l.snapshot_date
      and (p.status not in ('closed', 'canceled') or l.snapshot_date - p.actual_end <= 120)
),

joined as (
    select
        coalesce(e.project_id, r.project_id) as project_id,
        coalesce(e.project_code, r.project_ref) as project_ref,
        coalesce(e.team_code, r.sheet_team_code) as team_code,
        r.sheet_name,
        r.source_row,
        r.match_method,
        e.status as system_status,
        r.legacy_status as tracker_status,
        r.compatible_statuses,
        e.planned_end as system_planned_end,
        r.planned_end as tracker_planned_end,
        e.extension_count as system_extensions,
        r.extension_count as tracker_extensions,
        e.project_id is not null as expected_in_tracker,
        r.source_row is not null as listed_in_tracker
    from expected as e
    full outer join rows as r on e.project_id = r.project_id
)

select
    *,
    case
        when listed_in_tracker and project_id is null then 'not_in_system'
        when not listed_in_tracker then 'missing_in_tracker'
        when system_status is null then 'ok'  -- listed but archived-eligible in system; nothing to compare
        when not list_contains(coalesce(compatible_statuses, []), system_status) then 'status_mismatch'
        when tracker_planned_end is distinct from system_planned_end then 'end_date_mismatch'
        else 'ok'
    end as reconciliation_status,
    (select snapshot_week from latest) as snapshot_week
from joined
