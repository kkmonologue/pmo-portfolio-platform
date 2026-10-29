-- Tracker rows matched to the system: sheet -> team by name, row -> project by system
-- code or, for projects started before go-live, by legacy TRK code.
-- Excel cuts sheet names at 31 characters ("HQ - Technical Support & Warran"), so a
-- sheet matches the team whose name starts with the (possibly truncated) sheet name.
with rows as (
    select * from {{ ref('stg_tracker__rows') }} where not is_duplicate_row
),

teams as (
    select team_id, team_code, team_name from {{ ref('stg_app__teams') }}
),

projects as (
    select project_id, project_code, legacy_code, team_id, status, planned_end, extension_count
    from {{ ref('stg_app__projects') }}
    where not is_deleted
)

select
    r.*,
    t.team_id as sheet_team_id,
    t.team_code as sheet_team_code,
    p.project_id,
    case
        when p.project_id is null then 'unmatched'
        when r.project_ref = p.legacy_code then 'legacy_code'
        else 'project_code'
    end as match_method,
    p.status as system_status,
    p.planned_end as system_planned_end,
    p.extension_count as system_extension_count,
    p.team_id as system_team_id
from rows as r
left join teams as t on starts_with(t.team_name, r.sheet_team_name)
left join projects as p on r.project_ref in (p.project_code, upper(p.legacy_code))
