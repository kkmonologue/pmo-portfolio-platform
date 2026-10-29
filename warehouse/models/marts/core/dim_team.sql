with managers as (
    select tm.team_id, p.display_name as manager_name
    from {{ ref('stg_app__team_managers') }} as tm
    join {{ ref('stg_app__people') }} as p using (person_id)
    where tm.is_current and tm.section is null
)

select
    t.team_id,
    t.team_code,
    t.team_name,
    t.office,
    t.region,
    t.meeting_track,
    m.manager_name
from {{ ref('stg_app__teams') }} as t
left join managers as m using (team_id)
